import logging
import os

from fabric import Connection
from invoke import Responder


def createElasticsearchYml(pathToKey, pathToCrt, pathToCaCrt):
    """TODO: Docstring for createElasticsearchYml.

    :pathToKey: TODO
    :pathToCrt: TODO
    :pathToCaCrt: TODO
    :returns: TODO

    """
    configurationOptions = f"""#
# ----------------------- T-Pot Distributed Options ----------------------
#
cluster.name: t-pot-central
node.name: node1
network.host: 0.0.0.0
http.port: 64298
cluster.initial_master_nodes: ["node1"]
xpack.security.enabled: true

# internode communication (required if xpack.security is enabled)

xpack.security.transport.ssl.enabled: true
xpack.security.transport.ssl.verification_mode: certificate
xpack.security.transport.ssl.key: {pathToKey}
xpack.security.transport.ssl.certificate: {pathToCrt}
xpack.security.transport.ssl.certificate_authorities: [ \\"{pathToCaCrt}\\" ]

# client to node communication

xpack.security.http.ssl.enabled: true
xpack.security.http.ssl.verification_mode: certificate
xpack.security.http.ssl.key: {pathToKey}
xpack.security.http.ssl.certificate: {pathToCrt}
xpack.security.http.ssl.certificate_authorities: [ \\"{pathToCaCrt}\\" ]

# Workaround for logstash error Encountered a retryable error. Will retry with exponential backoff

http.max_content_length: 1gb"""

    return configurationOptions


def installTPot(conn, logger):
    """Install T-Pot Sensor type on connection server

    :conn: fabric.Connection object with connection to sensor server (4 GB RAM)
    :logger: logging.logger object
    :returns: None

    """
    conn.run("apt-get update && apt-get --yes upgrade", hide="stdout")
    conn.run("apt-get --yes install git", hide="stdout")
    logger.info("Updated packages and installed git")

    conn.run("git clone https://github.com/ezacl/tpotce-light /opt/tpot", hide="stdout")
    logger.info("Cloned T-Pot into /opt/tpot/")

    with conn.cd("/opt/tpot/"):
        conn.run("git checkout slim-standard", hide="stdout")
        logger.info("Checked out slim-standard branch")

        # trying to override logstash.conf to send data to remote elasticsearch
        # may need actually add a volume after all, will see
        conn.put("logstash.conf", remote="/opt/tpot/docker/elk/logstash/dist/")

        # with conn.cd("iso/installer/"):
        #     tPotInstall = conn.run(
        #         "./install.sh --type=auto --conf=tpot.conf", hide="stdout"
        #     )
        #     logger.info(tPotInstall.stdout.strip())

        #     if tPotInstall.ok:
        #         print("T-Pot installation successful.")
        #     else:
        #         print("T-Pot installation failed. See log file.")

        # need to reboot after all this too!!!!


def setupLoggingServer(conn, logger):
    """Install ELK stack and configure logging server to receive T-Pot data

    :conn: TODO
    :logger: TODO
    :returns: TODO

    """
    conn.run("apt-get update && apt-get --yes upgrade", hide="stdout")
    conn.run("apt-get --yes install gnupg apt-transport-https unzip", hide="stdout")
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
    conn.run(
        'echo "deb https://artifacts.elastic.co/packages/7.x/apt stable main"'
        " | tee /etc/apt/sources.list.d/elastic-7.x.list",
        hide="stdout",
    )
    conn.run("apt-get update", hide="stdout")
    # this one gives the same warning since it also uses apt-key, same fix
    conn.run("apt-get --yes install elasticsearch kibana", pty=True, hide="stdout")
    logger.info("Installed elasticsearch and kibana")

    hostname = conn.run("hostname", hide="stdout").stdout.strip()

    conn.run(
        f"/usr/share/elasticsearch/bin/elasticsearch-certutil cert --ip {conn.host}"
        f" --name {hostname} --out certificate-bundle.zip --pem",
        hide="stdout",
    )

    conn.run("mkdir /etc/elasticsearch/certs", hide="stdout")
    conn.run(
        "mv /usr/share/elasticsearch/certificate-bundle.zip /etc/elasticsearch/certs/",
        hide="stdout",
    )
    conn.run(
        "unzip /etc/elasticsearch/certs/certificate-bundle.zip"
        " -d /etc/elasticsearch/certs/",
        hide="stdout",
    )
    logger.info("Created and unzipped elasticsearch certificates")

    ymlConfig = createElasticsearchYml(
        f"certs/{hostname}/{hostname}.key",
        f"certs/{hostname}/{hostname}.crt",
        "certs/ca/ca.crt",
    )

    conn.run(
        f'echo -e "{ymlConfig}" >> /etc/elasticsearch/elasticsearch.yml', hide="stdout"
    )
    logger.info("Edited /etc/elasticsearch/elasticsearch.yml")

    conn.run("systemctl start elasticsearch.service", hide="stdout")
    logger.info("Started elasticsearch service with systemd")

    # I think I'm probably gonna need to wait for elasticsearch to boot up here
    # split up into multiple functions to be able to run them separately?

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
    logger.info(f"Generated ELK passwords, writing them to {pwdFile}.")

    with open(pwdFile, "w") as f:
        f.write(autoPasswords.stdout.strip())


if __name__ == "__main__":
    logFile = "fabric_logs.log"
    logging.basicConfig(
        filename=logFile,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    sensorPass = os.environ.get("SENSOR_PASS")
    logConn = Connection(
        host="167.71.246.62",
        user="root",
        connect_kwargs={"password": sensorPass}
        # host="167.71.92.145", user="root", connect_kwargs={"password": sensorPass}
    )
    sensorConn = Connection(
        host="159.203.169.33", user="root", connect_kwargs={"password": sensorPass}
    )

    # installTPot(sensorConn, logger)
    # setupLoggingServer(logConn, logger)
