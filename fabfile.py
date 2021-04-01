import json
import logging
import os
import sys
import time

from fabric import Config, Connection
from invoke import Responder
from invoke.config import Config as InvokeConfig
from invoke.context import Context
from invoke.exceptions import UnexpectedExit

from configFuncs import (createElasticsearchYml, createKibanaYml,
                         createLogstashConf, createUpdateCertsSh)
from deploymentHelpers import (createSudoUser, createTPotUser,
                               generateSSLCerts, importKibanaObjects,
                               installPackages, setupCurator, transferSSLCerts)
from errors import BadAPIRequestError, NoCredentialsFileError
from utils import findPassword, waitForService
from vmManagement import createAllVMs

logFile = "deployment.log"

logging.basicConfig(
    filename=logFile,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
# log to both stdout and log file
logger.addHandler(logging.StreamHandler(sys.stdout))


def installTPot(number, connection, certDir):
    """Install custom T-Pot Sensor type on connection server

    :number: index of sensor in deployNetwork for loop (for logging purposes)
    :connection: fabric.Connection object with connection to sensor server (4 GB RAM)
    :certDir: path to temporary directory containing SSL certificates
    :returns: None

    """
    packages = ["git"]
    installPackages(connection, packages)
    logger.info(f"Sensor {number}: Updated packages and installed git")

    # copy vimrc over for convenience
    connection.put("configFiles/.vimrc")
    connection.sudo("cp .vimrc /root/", hide=True)

    tPotPath = "/opt/tpot"

    # must clone into /opt/tpot/ because of altered install.sh script
    connection.sudo(
        f"git clone https://github.com/ezacl/tpotce-light {tPotPath}", hide=True
    )
    logger.info(f"Sensor {number}: Cloned T-Pot into {tPotPath}")

    # can add hide="stdout" as always but good to see real time output of
    # T-Pot installation
    connection.sudo(
        f"{tPotPath}/iso/installer/install.sh --type=auto"
        f" --conf={tPotPath}/iso/installer/tpot.conf"
    )
    logger.info(f"Sensor {number}: Installed T-Pot on sensor server")

    dataPath = "/data/elk"

    # copy custom logstash.conf into location where tpot.yml expects a docker volume
    connection.put("configFiles/logstash.conf")
    connection.sudo(f"mv logstash.conf {dataPath}/", hide=True)

    # copy SSL certificate over to sensor server
    transferSSLCerts(connection, certDir, loggingServer=False, dataPath=dataPath)
    logger.info(f"Sensor {number}: Copied SSL certificate from deployment server")

    # rebooting server always throws an exception, so ignore
    try:
        connection.sudo("reboot", hide=True)
    except UnexpectedExit:
        logger.info(f"Sensor {number}: Installed T-Pot and rebooted sensor server")


def installConfigureElasticsearch(
    conn, elasticPath, elasticCertsPath, kibanaPath, kibanaCertsPath, localCertDir
):
    """Install ELK stack and configure Elasticsearch on logging server

    :conn: fabric.Connection object with connection to logging server (8 GB RAM)
    :elasticPath: path to elasticsearch configuration directory
    :elasticCertsPath: path to elasticsearch SSL certificate directory
    :kibanaPath: path to kibana configuration directory
    :kibanaCertsPath: path to kibana SSL certificate directory
    :localCertDir: path to temporary directory containing SSL certificates
    :returns: None

    """
    elkDeps = ["gnupg", "apt-transport-https"]
    installPackages(conn, elkDeps)

    # copy vimrc over for convenience
    conn.put("configFiles/.vimrc")
    conn.sudo("cp .vimrc /root/", hide=True)

    logger.info("Logger: Updated packages and installed ELK dependencies")

    # download public signing keys
    artifactsKey = "elasticsearchArtifactsKey"
    packagesKey = "elasticsearchPackagesKey"
    conn.run(
        "wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch"
        f" > {artifactsKey}",
        hide="stdout",
    )
    conn.run(
        "wget -qO - https://packages.elastic.co/GPG-KEY-elasticsearch"
        f" > {packagesKey}",
        hide="stdout",
    )
    # install public signing keys
    # this gives
    # "Warning: apt-key output should not be parsed (stdout is not a terminal)"
    # can add pty=True to suppress it, but should find a fundamentally better way
    conn.sudo(f"apt-key add {artifactsKey}", pty=True, hide=True)
    conn.sudo(f"apt-key add {packagesKey}", pty=True, hide=True)
    conn.run(f"rm {artifactsKey} {packagesKey}", hide="stdout")

    # save repository definitions
    conn.run(
        'echo "deb https://artifacts.elastic.co/packages/7.x/apt stable main"'
        " > elastic-7.x.list",
        hide="stdout",
    )
    conn.run(
        'echo "deb [arch=amd64] https://packages.elastic.co/curator/5/debian9 stable'
        ' main" >> elastic-7.x.list',
        hide="stdout",
    )
    conn.sudo("mv elastic-7.x.list /etc/apt/sources.list.d/", hide=True)

    elkStack = ["elasticsearch", "kibana", "elasticsearch-curator"]
    installPackages(conn, elkStack)
    logger.info("Logger: Installed elasticsearch, kibana, and elasticsearch-curator")

    # transfer SSL certificates to loging server and put them in elasticsearch
    # and kibana config directories
    transferSSLCerts(
        conn,
        localCertDir,
        loggingServer=True,
        elasticPath=elasticPath,
        elasticCertsPath=elasticCertsPath,
        kibanaPath=kibanaPath,
        kibanaCertsPath=kibanaCertsPath,
    )

    logger.info(
        "Logger: Transferred SSL certificates to"
        f" {elasticCertsPath} and {kibanaCertsPath}"
    )

    ymlConfigPath = createElasticsearchYml(
        f"{elasticCertsPath}/privkey.pem",
        f"{elasticCertsPath}/cert.pem",
        f"{elasticCertsPath}/fullchain.pem",
    )

    # overwrite elasticsearch.yml in config directory
    conn.put(ymlConfigPath)
    conn.sudo(f"mv elasticsearch.yml {elasticPath}/elasticsearch.yml", hide=True)
    logger.info(f"Logger: Edited {elasticPath}/elasticsearch.yml")

    conn.sudo("systemctl start elasticsearch.service", hide=True)
    logger.info("Logger: Started elasticsearch service with systemd")


def configureKibana(conn, kibanaPath, kibanaCertsPath):
    """Configure Kibana on logging server to connect it with Elasticsearch (must be run
    after installConfigureElasticsearch function)

    :conn: fabric.Connection object with connection to logging server (8 GB RAM)
    :kibanaPath: path to kibana configuration directory
    :kibanaCertsPath: path to kibana SSL certificate directory
    :returns: password for elastic user, useful to make subsequent API calls

    """
    # elasticsearch-setup-passwords needs user input even in auto mode, so mock it
    pwdSetupYes = Responder(
        pattern=r"Please confirm that you would like to continue \[y/N\]",
        response="y\n",
    )
    # create passwords for all ELK-related users
    autoPasswords = conn.sudo(
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

    # set up elasticsearch-curator to delete old logstash indices
    curatorPath = "/opt/elasticsearch-curator/"
    setupCurator(conn, curatorPath, elasticPass)
    logger.info("Logger: Set up elasticsearch-curator to delete old indices")

    ymlConfigPath = createKibanaYml(
        conn.host,
        kibanaPass,
        f"{kibanaCertsPath}/privkey.pem",
        f"{kibanaCertsPath}/fullchain.pem",
    )

    # overwrite kibana.yml in config directory
    conn.put(ymlConfigPath)
    conn.sudo(f"mv kibana.yml {kibanaPath}/kibana.yml", hide=True)
    logger.info(f"Logger: Edited {kibanaPath}/kibana.yml")

    conn.sudo("systemctl restart elasticsearch.service", hide=True)
    conn.sudo("systemctl start kibana.service", hide=True)
    logger.info("Logger: Started elasticsearch and kibana services with systemd")

    return elasticPass


def configureLoggingServer(connection, localCertDir):
    """Completely set up logging server for it to be ready to receive honeypot data
    from sensor servers

    :connection: fabric.Connection object with connection to logging server (8 GB RAM)
    :localCertDir: path to temporary directory containing SSL certificates
    :returns: None

    """

    elasticPath = "/etc/elasticsearch"
    elasticCertsPath = f"{elasticPath}/certs"
    kibanaPath = "/etc/kibana"
    kibanaCertsPath = f"{kibanaPath}/certs"

    installConfigureElasticsearch(
        connection,
        elasticPath,
        elasticCertsPath,
        kibanaPath,
        kibanaCertsPath,
        localCertDir,
    )

    # block until elasticsearch service (port 64298) is ready
    waitForService(connection.host, 64298)

    elasticPass = configureKibana(connection, kibanaPath, kibanaCertsPath)

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
            f"\nPASSWORD {tPotUser} = {tPotPass}\n"
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


def createAllSudoUsers(sensorObjects, sudoUser, loggingObject=None):
    """Create non-root sudo users on all servers in network

    :sensorObjects: list of sensor server dictionaries from credentials.json
    :sudoUser: Name of non-root sudo user to create on all servers
    :loggingObject: optional, logging server dictionary from credentials.json
    :returns: None

    """
    objsList = (
        [loggingObject] + sensorObjects if loggingObject is not None else sensorObjects
    )

    for creds in objsList:
        host = creds["host"]
        conn = Connection(host=host, user="root")
        createSudoUser(conn, sudoUser, creds["sudopass"])
        conn.close()

        logger.info(f"Created non-root sudo user {sudoUser}@{host}")


def deployNetwork(
    loggingServer=True, credsFile="credentials.json", DOApiKeyFile="digitalocean.ini"
):
    """Set up entire distributed T-Pot network with logging and sensor servers

    :loggingServer: optional, whether to set up central logging server. Defaults to
    True. Set to False if you already have deployed a logging server and want to
    only add sensor server(s)
    :credsFile: optional, path to credentials JSON file. Defaults to credentials.json
    :DOApiKeyFile: optional, path to file containing DigitalOcean API key. Defaults to
    digitalocean.ini
    :returns: None

    """
    try:
        # get server credentials from credentials file
        with open(credsFile) as f:
            credentials = json.load(f)
            deploymentCreds = credentials["deployment"]
            logCreds = credentials["logging"]
            sensorCreds = credentials["sensors"]
            tPotSudoUser = credentials["sudouser"]
    except FileNotFoundError:
        raise NoCredentialsFileError(
            f"{credsFile} not found. Did you copy credentials.json.template?"
        )

    # get DigitalOcean API key
    with open(DOApiKeyFile) as f:
        apiKey = f.read().strip().split()[-1]

    deploymentConf = InvokeConfig()
    deploymentConf.sudo.password = deploymentCreds["sudopass"]
    deploymentConn = Context(config=deploymentConf)

    # generate SSH keys to log into network servers
    deploymentConn.run(
        "ssh-keygen -f ~/.ssh/id_rsa -t rsa -b 4096 -N ''", hide="stdout"
    )
    logger.info("Deployment: generated SSH keys for network servers")
    sshKey = deploymentConn.run("cat ~/.ssh/id_rsa.pub", hide="stdout").stdout.strip()
    # create all network servers specified in credentials.json
    createAllVMs(apiKey, logCreds, sensorCreds, sshKey)
    logger.info("Deployment: Created all network servers through DigitalOcean API")

    tempCertPath = generateSSLCerts(
        deploymentConn,
        deploymentCreds["email"],
        logCreds["host"],
        f"{os.getcwd()}/{DOApiKeyFile}",
    )
    logger.info(
        "Deployment: created Let's Encrypt SSL certificates and made temporary"
        f"SSL certificate directory {tempCertPath}"
    )

    sudoUser = deploymentConn.run("whoami", hide="stdout").stdout.strip()
    certsWrapperPath = createUpdateCertsSh(os.getcwd(), sudoUser)
    renewHookPath = "/etc/letsencrypt/renewal-hooks/deploy/updateCerts.sh"
    deploymentConn.sudo(f"cp {certsWrapperPath} {renewHookPath}", hide=True)
    deploymentConn.sudo(f"chmod u+x {renewHookPath}", hide=True)
    logger.info(f"Deployment: Added custom SSL renewal script to {renewHookPath}")

    if loggingServer:
        createAllSudoUsers(sensorCreds, tPotSudoUser, logCreds)
    else:
        createAllSudoUsers(sensorCreds, tPotSudoUser)

    logConn = Connection(
        host=logCreds["host"],
        user=tPotSudoUser,
        config=Config(overrides={"sudo": {"password": logCreds["sudopass"]}}),
    )

    if loggingServer:
        # set up central logging server
        configureLoggingServer(logConn, tempCertPath)

    logConn.close()

    # set up all sensor servers (make this async?)
    for index, sensor in enumerate(sensorCreds):
        sensorConn = Connection(
            host=sensor["host"],
            user=tPotSudoUser,
            config=Config(overrides={"sudo": {"password": sensor["sudopass"]}}),
        )
        installTPot(index + 1, sensorConn, tempCertPath)

        sensorConn.close()

    # should probably chmod the whole directory since passwords are everywhere TODO
    deploymentConn.run("chmod 600 passwords.txt credentials.json")
    # remove temporarily copied SSL certs from generateSSLCerts
    deploymentConn.run(f"rm -rf {tempCertPath}", hide="stdout")
    logger.info(f"Removed temporary SSL certificate directory {tempCertPath}")


if __name__ == "__main__":
    deployNetwork()
