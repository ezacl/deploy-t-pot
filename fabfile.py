import logging
import os

from fabric import Connection


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

        with conn.cd("iso/installer/"):
            tPotInstall = conn.run(
                "./install.sh --type=auto --conf=tpot.conf", hide="stdout"
            )
            logger.info(tPotInstall.stdout.strip())

            if tPotInstall.ok:
                print("T-Pot installation successful.")
            else:
                print("T-Pot installation failed. See log file.")


if __name__ == "__main__":
    logFile = "fabric_logs.log"
    logging.basicConfig(
        filename=logFile,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    sensorPass = os.environ.get("SENSOR_PASS")
    connection = Connection(
        # host="167.71.92.145", user="root", connect_kwargs={"password": sensorPass}
        host="159.203.169.33",
        user="root",
        connect_kwargs={"password": sensorPass},
    )

    # installTPot(connection, logger)
