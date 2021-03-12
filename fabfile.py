import logging
import os

from fabric import Connection
from invoke import Responder
from invoke.exceptions import UnexpectedExit

from configFuncs import createElasticsearchYml, createKibanaYml


def installTPot(sensorConn, loggingConn, logger):
    """Install T-Pot Sensor type on connection server

    :sensorConn: fabric.Connection object with connection to sensor server (4 GB RAM)
    :logingConn: fabric.Connection object with connection to logging server (8 GB RAM)
    :logger: logging.logger object
    :returns: None

    """
    sensorConn.run("apt-get update && apt-get --yes upgrade", pty=True, hide="stdout")
    sensorConn.run("apt-get --yes install git", pty=True, hide="stdout")
    logger.info("Updated packages and installed git")

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
    sensorConn.put("logstash.conf", remote="/data/elk/")

    loggingConn.get("/etc/elasticsearch/certs/ca/ca.crt")
    sensorConn.put("ca.crt", remote="/data/elk/ca.crt")
    os.remove("ca.crt")
    logger.info("Copied certificates from logging server")

    # rebooting server always throws an exception, so ignore
    try:
        sensorConn.run("reboot", hide="stdout")
    except UnexpectedExit:
        logger.info("Installed T-Pot and rebooted sensor server")


def installConfigureElasticsearch(conn, email, logger):
    """Install ELK stack and configure Elasticsearch on logging server

    :conn: TODO
    :email: TODO
    :logger: TODO
    :returns: TODO

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
    ymlConfig = createElasticsearchYml(
        "/etc/elasticsearch/certs/privkey.pem",
        "/etc/elasticsearch/certs/cert.pem",
        "/etc/elasticsearch/certs/fullchain.pem",
    )

    conn.run(
        f'echo -e "{ymlConfig}" >> /etc/elasticsearch/elasticsearch.yml', hide="stdout"
    )
    logger.info("Edited /etc/elasticsearch/elasticsearch.yml")

    conn.run("systemctl start elasticsearch.service", hide="stdout")
    logger.info("Started elasticsearch service with systemd")


def configureKibana(conn, logger):
    """Configure Kibana on logging server to connect it with Elasticsearch

    ### MUST RUN installConfigureElasticsearch BEFORE (AND PROBABLY WAIT AFTER) ###

    should try to set up wait-for to be able to confidently run this function

    :conn: TODO
    :logger: TODO
    :returns: TODO

    """
    pwdSetupYes = Responder(
        pattern=r"Please confirm that you would like to continue \[y/N\]",
        response="y\n",
    )
    autoPasswords = conn.run(
        "/usr/share/elasticsearch/bin/elasticsearch-setup-passwords auto",
        pty=True,
        watchers=[pwdSetupYes],
    )
    pwdFile = "elasticsearch_passwords.txt"
    logger.info(f"Generated ELK passwords, writing them to {pwdFile}")

    pwdRes = autoPasswords.stdout.strip()

    with open(pwdFile, "w") as f:
        f.write(pwdRes)

    try:
        # extract password for kibana_system user to put in kibana.yml
        kibanaPwdSearch = "PASSWORD kibana_system = "

        startInd = pwdRes.index(kibanaPwdSearch) + len(kibanaPwdSearch)
        trimmedPwd = pwdRes[startInd:]
        endInd = trimmedPwd.index("\n")

        kibanaPass = trimmedPwd[:endInd].strip()
    except ValueError:
        raise Exception(
            "kibana_system password not created by elasticsearch-setup-passwords"
        )

    # copying certificates isn't good but I couldn't get it to work with symlinks
    conn.run("cp -r /etc/elasticsearch/certs /etc/kibana/", hide="stdout")
    logger.info("Copied elasticsearch certificates to /etc/kibana")

    # avoid hardcoding paths again
    ymlConfig = createKibanaYml(
        conn.host,
        kibanaPass,
        "/etc/kibana/certs/privkey.pem",
        "/etc/kibana/certs/cert.pem",
    )

    conn.run(f'echo -e "{ymlConfig}" >> /etc/kibana/kibana.yml', hide="stdout")
    logger.info("Edited /etc/kibana/kibana.yml")

    conn.run("systemctl restart elasticsearch.service", hide="stdout")
    conn.run("systemctl start kibana.service", hide="stdout")
    logger.info("Started elasticsearch and kibana services with systemd")


def createTPotUser(conn):
    """TODO: Docstring for createTPotUser.

    :conn: TODO
    :returns: TODO

    """
    # create the logstash_writer and logstash_internal role and user, respectively
    # see createRoles.txt
    pass


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
    sensorPass = os.environ.get("SENSOR_PASS")
    logConn = Connection(
        host=logHost, user="root", connect_kwargs={"password": sensorPass}
    )
    # sensorConn = Connection(
    #     host="167.71.101.194", user="root", connect_kwargs={"password": sensorPass}
    # )
    sensorConn = Connection(
        host="134.122.8.182", user="root", connect_kwargs={"password": sensorPass}
    )

    # installTPot(sensorConn, logConn, logger)
    # installConfigureElasticsearch(logConn, email, logger)
    # configureKibana(logConn, logger)
