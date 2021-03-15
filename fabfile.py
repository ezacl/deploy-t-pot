import logging
import os
import time

from fabric import Connection
from invoke import Responder
from invoke.exceptions import UnexpectedExit

from configFuncs import (createElasticsearchYml, createKibanaYml,
                         createLogstashConf, createTPotUser,
                         importKibanaObjects)
from utils import findPassword, waitForService


def installTPot(sensorConn, loggingConn, logger):
    """Install custom T-Pot Sensor type on connection server

    :sensorConn: fabric.Connection object with connection to sensor server (4 GB RAM)
    :logingConn: fabric.Connection object with connection to logging server (8 GB RAM)
    :logger: logging.logger object
    :returns: None

    """
    sensorConn.run("apt-get update && apt-get --yes upgrade", pty=True, hide="stdout")
    sensorConn.run("apt-get --yes install git", pty=True, hide="stdout")
    logger.info("Updated packages and installed git")

    # must clone into /opt/tpot because of altered install.sh script
    sensorConn.run(
        "git clone https://github.com/ezacl/tpotce-light /opt/tpot", hide="stdout"
    )
    logger.info("Cloned T-Pot into /opt/tpot/")

    with sensorConn.cd("/opt/tpot/"):
        sensorConn.run("git checkout slim-standard", hide="stdout")
        logger.info("Checked out slim-standard branch")

        with sensorConn.cd("iso/installer/"):
            # can add hide="stdout" as always but good to see real time output of
            # T-Pot installation
            tPotInstall = sensorConn.run("./install.sh --type=auto --conf=tpot.conf")
            logger.info(tPotInstall.stdout.strip())

            if tPotInstall.ok:
                print("T-Pot installation successful.")
            else:
                print("T-Pot installation failed. See log file.")

    # copy custom logstash.conf into location where tpot.yml expects a docker volume
    sensorConn.put("configFiles/logstash.conf", remote="/data/elk/")

    # copy SSL certificate over
    loggingConn.get("/etc/elasticsearch/certs/fullchain.pem")
    sensorConn.put("fullchain.pem", remote="/data/elk/")
    os.remove("fullchain.pem")
    logger.info("Copied certificate from logging server")

    # rebooting server always throws an exception, so ignore
    try:
        sensorConn.run("reboot", hide="stdout")
    except UnexpectedExit:
        logger.info("Installed T-Pot and rebooted sensor server")


def installConfigureElasticsearch(conn, email, logger):
    """Install ELK stack and configure Elasticsearch on logging server

    :conn: fabric.Connection object with connection to logging server (8 GB RAM)
    :email: email address to receive Certbot notifications
    :logger: logging.logger object
    :returns: None

    """
    conn.run("apt-get update && apt-get --yes upgrade", pty=True, hide="stdout")
    conn.run(
        "apt-get --yes install gnupg apt-transport-https certbot",
        pty=True,
        hide="stdout",
    )
    conn.run(
        "wget https://raw.githubusercontent.com/ezacl/"
        "tpotce-light/slim-standard/.vimrc",
        hide=True,
    )
    logger.info("Updated packages and installed ELK dependencies")

    # this gives
    # "Warning: apt-key output should not be parsed (stdout is not a terminal)"
    # can add pty=True to suppress it, but should find a fundamentally better way
    conn.run(
        "wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch"
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
    conn.run("apt-get update", hide="stdout")
    # this one gives the same warning since it also uses apt-key, same fix
    conn.run("apt-get --yes install elasticsearch kibana", pty=True, hide="stdout")
    logger.info("Installed elasticsearch and kibana")

    conn.run("mkdir /etc/elasticsearch/certs", hide="stdout")

    # will have to look into auto-renewing certificates
    # https://www.digitalocean.com/community/tutorials/how-to-use-certbot-standalone-mode-to-retrieve-let-s-encrypt-ssl-certificates-on-debian-10
    conn.run(
        f"certbot certonly --standalone -d {conn.host} --non-interactive"
        f" --agree-tos --email {email}",
        hide="stdout",
    )

    # tried to symlink these instead, but kept on getting permission errors in ES logs
    conn.run(
        f"cp /etc/letsencrypt/live/{conn.host}/* /etc/elasticsearch/certs/",
        hide="stdout",
    )
    conn.run("chmod 644 /etc/elasticsearch/certs/privkey.pem", hide="stdout")
    logger.info("Created elasticsearch certificates")

    # avoid hardcoding this
    ymlConfigPath = createElasticsearchYml(
        "/etc/elasticsearch/certs/privkey.pem",
        "/etc/elasticsearch/certs/cert.pem",
        "/etc/elasticsearch/certs/fullchain.pem",
    )

    # overwrite elasticsearch.yml in config directory
    conn.put(ymlConfigPath, remote="/etc/elasticsearch/elasticsearch.yml")
    logger.info("Edited /etc/elasticsearch/elasticsearch.yml")

    conn.run("systemctl start elasticsearch.service", hide="stdout")
    logger.info("Started elasticsearch service with systemd")


def configureKibana(conn, logger):
    """Configure Kibana on logging server to connect it with Elasticsearch (must be run
    after installConfigureElasticsearch function)

    :conn: fabric.Connection object with connection to logging server (8 GB RAM)
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
    logger.info(f"Generated ELK passwords, writing them to {pwdFile}")

    pwdRes = autoPasswords.stdout.strip()

    with open(pwdFile, "w") as f:
        f.write(pwdRes)

    kibanaPass = findPassword(pwdRes, "kibana_system")
    elasticPass = findPassword(pwdRes, "elastic")

    # copying certificates isn't good but I couldn't get it to work with symlinks
    conn.run("cp -r /etc/elasticsearch/certs /etc/kibana/", hide="stdout")
    logger.info("Copied elasticsearch certificates to /etc/kibana")

    # avoid hardcoding paths again
    ymlConfigPath = createKibanaYml(
        conn.host,
        kibanaPass,
        "/etc/kibana/certs/privkey.pem",
        "/etc/kibana/certs/fullchain.pem",
    )

    # overwrite kibana.yml in config directory
    conn.put(ymlConfigPath, remote="/etc/kibana/kibana.yml")
    logger.info("Edited /etc/kibana/kibana.yml")

    conn.run("systemctl restart elasticsearch.service", hide="stdout")
    conn.run("systemctl start kibana.service", hide="stdout")
    logger.info("Started elasticsearch and kibana services with systemd")

    return elasticPass


def configureLoggingServer(connection, email, logger):
    """Completely set up logging server for it to be ready to receive honeypot data
    from sensor servers

    :connection: fabric.Connection object with connection to logging server (8 GB RAM)
    :email: email address to receive Certbot notifications
    :logger: logging.logger object
    :returns: None

    """
    installConfigureElasticsearch(connection, email, logger)

    # block until elasticsearch service (port 64298) is ready
    waitForService(connection.host, 64298)

    elasticPass = configureKibana(connection, logger)

    waitForService(connection.host, 64298)

    try:
        # making an API call too early causes an error, hence catching it and waiting
        tPotUser, tPotPass = createTPotUser(
            f"{connection.host}:64298", "elastic", elasticPass
        )
    # make this a more precise error
    except Exception:
        time.sleep(10)

        tPotUser, tPotPass = createTPotUser(
            f"{connection.host}:64298", "elastic", elasticPass
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
    importKibanaObjects(
        f"{connection.host}:5601", "elastic", elasticPass, "kibanaTemplate.ndjson"
    )


if __name__ == "__main__":
    logFile = "fabric_logs.log"
    logging.basicConfig(
        filename=logFile,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    logHost = os.environ.get("LOGGING_HOST")
    email = os.environ.get("LOGGING_EMAIL")
    logPass = os.environ.get("LOGGING_PASS")
    sensorPass = os.environ.get("SENSOR_PASS")
    sensorHost = os.environ.get("SENSOR_HOST")
    logConn = Connection(
        host=logHost, user="root", connect_kwargs={"password": logPass}
    )
    sensorConn = Connection(
        host=sensorHost, user="root", connect_kwargs={"password": sensorPass}
    )

    configureLoggingServer(logConn, email, logger)
    installTPot(sensorConn, logConn, logger)
