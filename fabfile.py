import json
import logging
import os
import time

from fabric import Connection
from invoke import Responder
from invoke.exceptions import UnexpectedExit

from configFuncs import (createCuratorConfigYml, createElasticsearchYml,
                         createKibanaYml, createLogstashConf, createTPotUser,
                         createUpdateCertsSh, importKibanaObjects)
from errors import BadAPIRequestError, NoCredentialsFileError
from utils import findPassword, waitForService


def installTPot(number, sensorConn, loggingConn, logger):
    """Install custom T-Pot Sensor type on connection server

    :number: index of sensor in deployNetwork for loop (for logging purposes)
    :sensorConn: fabric.Connection object with connection to sensor server (4 GB RAM)
    :logingConn: fabric.Connection object with connection to logging server (8 GB RAM)
    :logger: logging.logger object
    :returns: None

    """
    sensorConn.run("apt-get update && apt-get --yes upgrade", pty=True, hide="stdout")
    sensorConn.run("apt-get --yes install git", pty=True, hide="stdout")
    logger.info(f"Sensor {number}: Updated packages and installed git")

    # copy vimrc over for convenience
    sensorConn.put("configFiles/.vimrc")

    # copy SSH public key to sensor server to transfer files from logging server
    sensorConn.put("id_rsa.pub", remote=".ssh/authorized_keys")

    tPotPath = "/opt/tpot"

    # must clone into /opt/tpot/ because of altered install.sh script
    sensorConn.run(
        f"git clone https://github.com/ezacl/tpotce-light {tPotPath}", hide="stdout"
    )
    logger.info(f"Sensor {number}: Cloned T-Pot into {tPotPath}")

    with sensorConn.cd(f"{tPotPath}/iso/installer/"):
        # can add hide="stdout" as always but good to see real time output of
        # T-Pot installation
        sensorConn.run("./install.sh --type=auto --conf=tpot.conf")
        logger.info(f"Sensor {number}: Installed T-Pot on sensor server")

    dataPath = "/data/elk/"

    # copy custom logstash.conf into location where tpot.yml expects a docker volume
    sensorConn.put("configFiles/logstash.conf", remote=dataPath)

    # copy SSL certificate over (copied to local machine in deployNetwork)
    sensorConn.put("fullchain.pem", remote=dataPath)
    logger.info(f"Sensor {number}: Copied certificate from logging server")

    # rebooting server always throws an exception, so ignore
    try:
        sensorConn.run("reboot", hide="stdout")
    except UnexpectedExit:
        logger.info(f"Sensor {number}: Installed T-Pot and rebooted sensor server")


def installConfigureElasticsearch(conn, email, elasticPath, elasticCertsPath, logger):
    """Install ELK stack and configure Elasticsearch on logging server

    :conn: fabric.Connection object with connection to logging server (8 GB RAM)
    :email: email address to receive Certbot notifications
    :elasticPath: path to elasticsearch configuration directory
    :elasticPath: path to elasticsearch SSL certificate directory
    :logger: logging.logger object
    :returns: None

    """
    elkDeps = "gnupg apt-transport-https certbot"

    conn.run("apt-get update && apt-get --yes upgrade", pty=True, hide="stdout")
    conn.run(
        f"apt-get --yes install {elkDeps}",
        pty=True,
        hide="stdout",
    )

    # copy vimrc over for convenience
    conn.put("configFiles/.vimrc")

    logger.info("Logger: Updated packages and installed ELK dependencies")

    # this gives
    # "Warning: apt-key output should not be parsed (stdout is not a terminal)"
    # can add pty=True to suppress it, but should find a fundamentally better way
    conn.run(
        "wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch"
        " | apt-key add -",
        pty=True,
        hide="stdout",
    )
    conn.run(
        "wget -qO - https://packages.elastic.co/GPG-KEY-elasticsearch"
        " | apt-key add -",
        pty=True,
        hide="stdout",
    )
    # this needs sudo tee if not already run as root
    conn.run(
        'echo "deb https://artifacts.elastic.co/packages/7.x/apt stable main"'
        " | tee /etc/apt/sources.list.d/elastic-7.x.list",
        hide="stdout",
    )
    conn.run(
        'echo "deb [arch=amd64] https://packages.elastic.co/curator/5/debian9 stable'
        ' main" >> /etc/apt/sources.list.d/elastic-7.x.list',
        hide="stdout",
    )
    conn.run("apt-get update", hide="stdout")
    # this one gives the same warning since it also uses apt-key, same fix
    conn.run(
        "apt-get --yes install elasticsearch kibana elasticsearch-curator",
        pty=True,
        hide="stdout",
    )
    logger.info("Logger: Installed elasticsearch and kibana")

    conn.run(f"mkdir {elasticCertsPath}", hide="stdout")

    # will have to look into auto-renewing certificates
    # https://www.digitalocean.com/community/tutorials/how-to-use-certbot-standalone-mode-to-retrieve-let-s-encrypt-ssl-certificates-on-debian-10
    conn.run(
        f"certbot certonly --standalone -d {conn.host} --non-interactive"
        f" --agree-tos --email {email}",
        hide="stdout",
    )

    # tried to symlink these instead, but kept on getting permission errors in ES logs
    conn.run(
        f"cp /etc/letsencrypt/live/{conn.host}/* {elasticCertsPath}/",
        hide="stdout",
    )
    conn.run(f"chmod 644 {elasticCertsPath}/privkey.pem", hide="stdout")

    logger.info("Logger: Created elasticsearch certificates")

    ymlConfigPath = createElasticsearchYml(
        f"{elasticCertsPath}/privkey.pem",
        f"{elasticCertsPath}/cert.pem",
        f"{elasticCertsPath}/fullchain.pem",
    )

    # overwrite elasticsearch.yml in config directory
    conn.put(ymlConfigPath, remote=f"{elasticPath}/elasticsearch.yml")
    logger.info(f"Logger: Edited {elasticPath}/elasticsearch.yml")

    conn.run("systemctl start elasticsearch.service", hide="stdout")
    logger.info("Logger: Started elasticsearch service with systemd")


def configureKibana(conn, kibanaPath, logger):
    """Configure Kibana on logging server to connect it with Elasticsearch (must be run
    after installConfigureElasticsearch function)

    :conn: fabric.Connection object with connection to logging server (8 GB RAM)
    :kibanaPath: path to kibana configuration directory
    :logger: logging.logger object
    :returns: password for elastic user, useful to make subsequent API calls

    """
    # elasticsearch-setup-passwords needs user input even in auto mode, so mock it
    pwdSetupYes = Responder(
        pattern=r"Please confirm that you would like to continue \[y/N\]",
        response="y\n",
    )
    # create passwords for all ELK-related users
    autoPasswords = conn.run(
        "/usr/share/elasticsearch/bin/elasticsearch-setup-passwords auto",
        pty=True,
        watchers=[pwdSetupYes],
    )
    pwdFile = "passwords.txt"
    logger.info(f"Logger: Generated ELK passwords, writing them to {pwdFile}")

    pwdRes = autoPasswords.stdout.strip()

    with open(pwdFile, "w") as f:
        f.write(pwdRes)

    kibanaPass = findPassword(pwdRes, "kibana_system")
    elasticPass = findPassword(pwdRes, "elastic")

    # commands to set up elasticsearch-curator to delete old indices
    curatorPath = "/opt/elasticsearch-curator/"
    conn.run("mkdir /var/log/curator", hide="stdout")

    curatorConfigPath = createCuratorConfigYml(conn.host, elasticPass)
    conn.put(curatorConfigPath, remote=curatorPath)
    conn.put("configFiles/curatorActions.yml", remote=curatorPath)

    # add cronjob to run curator every day at midnight
    curatorCommand = (
        f"curator --config {curatorPath}curatorConfig.yml"
        f" {curatorPath}curatorActions.yml"
    )
    conn.run(f'echo "{curatorCommand}" >> /etc/crontab')

    logger.info("Logger: Set up elasticsearch-curator to delete old indices")

    kibanaCertsPath = f"{kibanaPath}/certs"

    # copying certificates isn't good but I couldn't get it to work with symlinks
    conn.run(f"cp -r /etc/elasticsearch/certs {kibanaPath}/", hide="stdout")
    logger.info(f"Logger: Copied elasticsearch certificates to {kibanaCertsPath}")

    ymlConfigPath = createKibanaYml(
        conn.host,
        kibanaPass,
        f"{kibanaCertsPath}/privkey.pem",
        f"{kibanaCertsPath}/fullchain.pem",
    )

    # overwrite kibana.yml in config directory
    conn.put(ymlConfigPath, remote=f"{kibanaPath}/kibana.yml")
    logger.info(f"Logger: Edited {kibanaPath}/kibana.yml")

    conn.run("systemctl restart elasticsearch.service", hide="stdout")
    conn.run("systemctl start kibana.service", hide="stdout")
    logger.info("Logger: Started elasticsearch and kibana services with systemd")

    return elasticPass


def configureLoggingServer(connection, sensorDomains, email, logger):
    """Completely set up logging server for it to be ready to receive honeypot data
    from sensor servers

    :connection: fabric.Connection object with connection to logging server (8 GB RAM)
    :sensorDomains: list of FQDNs or IP addresses of sensor servers
    :email: email address to receive Certbot notifications
    :logger: logging.logger object
    :returns: None

    """
    # generate SSH key
    connection.run("ssh-keygen -f ~/.ssh/id_rsa -t rsa -N ''", hide="stdout")

    elasticPath = "/etc/elasticsearch"
    elasticCertsPath = f"{elasticPath}/certs"
    kibanaPath = "/etc/kibana"

    installConfigureElasticsearch(
        connection, email, elasticPath, elasticCertsPath, logger
    )

    # create custom SSL renewal shell script and copy it to logging server
    updateShPath = createUpdateCertsSh(
        connection.host, sensorDomains, elasticCertsPath, kibanaPath
    )
    renewHookPath = "/etc/letsencrypt/renewal-hooks/deploy/updateCerts.sh"
    connection.put(updateShPath, remote=renewHookPath)
    connection.run(f"chmod +x {renewHookPath}", hide="stdout")

    # block until elasticsearch service (port 64298) is ready
    waitForService(connection.host, 64298)

    elasticPass = configureKibana(connection, kibanaPath, logger)

    waitForService(connection.host, 64298)

    try:
        # making an API call too early causes an error, hence catching it and waiting
        tPotUser, tPotPass = createTPotUser(
            f"{connection.host}:64298", "elastic", elasticPass
        )
    except BadAPIRequestError:
        time.sleep(10)

        tPotUser, tPotPass = createTPotUser(
            f"{connection.host}:64298", "elastic", elasticPass
        )

    logger.info(
        f"Logger: Created {tPotUser} Elasticsearch user with corresponding role"
    )

    # logstash.conf later gets copied over to each sensor server
    createLogstashConf(connection.host, "/data/elk/fullchain.pem", tPotUser, tPotPass)

    # add password for t_pot_internal user (which sensor servers use to send data)
    with open("passwords.txt", "a") as f:
        f.write(
            f"\n\nChanged password for user {tPotUser}"
            f"\nPASSWORD {tPotUser} = {tPotPass}"
        )

    # block until kibana service (port 5601) is ready
    waitForService(connection.host, 5601)

    # convenience function to copy nice honeypot attack visualizations to kibana
    # dashboard. Uses an experimental ELK API, so just comment out if it breaks in
    # the future
    importKibanaObjects(f"{connection.host}:5601", "elastic", elasticPass)

    logger.info(
        "Logger: Imported custom objects into Kibana dashboard and turned on dark mode"
    )


def deployNetwork(
    loggingServer=True, credsFile="credentials.json", logFile="fabric_logs.log"
):
    """Set up entire distributed T-Pot network with logging and sensor servers

    :loggingServer: optional, whether to set up central logging server. Defaults to
    True. Set to False if you already have deployed a logging server and want to
    only add sensor server(s)
    :credsFile: optional, path to credentials JSON file. Defaults to credentials.json
    :logFile: optional, path to log file. Defaults to fabric_logs.log
    :returns: None

    """
    try:
        # get server credentials from credentials file
        with open(credsFile) as f:
            credentials = json.load(f)
            logCreds = credentials["logging"]
            sensorCreds = credentials["sensors"]
    except FileNotFoundError:
        raise NoCredentialsFileError(
            f"{credsFile} not found. Did you copy credentials.json.template?"
        )

    logging.basicConfig(
        filename=logFile,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    logConn = Connection(
        host=logCreds["host"],
        user="root",
        connect_kwargs={"password": logCreds["password"]},
    )
    if loggingServer:
        # set up central logging server
        sensorHosts = [sensor["host"] for sensor in sensorCreds]
        configureLoggingServer(logConn, sensorHosts, logCreds["email"], logger)

    # retrieve SSL certificate and SSH public key from logging server
    logConn.get("/etc/elasticsearch/certs/fullchain.pem")
    logConn.get(".ssh/id_rsa.pub")

    # set up all sensor servers (make this async soon?)
    for index, sensor in enumerate(sensorCreds):
        sensorConn = Connection(
            host=sensor["host"],
            user="root",
            connect_kwargs={"password": sensor["password"]},
        )
        installTPot(index + 1, sensorConn, logConn, logger)

        sensorConn.close()

    logConn.close()

    os.remove("fullchain.pem")
    os.remove("id_rsa.pub")


if __name__ == "__main__":
    deployNetwork()
