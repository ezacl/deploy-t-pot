import json
import os
import sys

from fabric import Config, Connection
from invoke.config import Config as InvokeConfig
from invoke.context import Context

from deploymentHelpers import transferSSLCerts

# Fabric script to automatically handle SSL certificate renewal with ELK services
# check logs at /var/log/letsencrypt/letsencrypt.log for debugging

# change working directory to command-line argument to be able to find config files
os.chdir(sys.argv[1])

credsFile = "credentials.json"

with open(credsFile) as f:
    credentials = json.load(f)
    deploymentCreds = credentials["deployment"]
    logCreds = credentials["logging"]
    sensorCreds = credentials["sensors"]

loggingHost = logCreds["host"]
sudoUser = credentials["sudouser"]

deploymentConf = InvokeConfig()
deploymentConf.sudo.password = deploymentCreds["sudopass"]
deploymentConn = Context(config=deploymentConf)

tempCertPath = "tempCerts"
deploymentConn.run(f"mkdir {tempCertPath}", hide="stdout")
deploymentConn.sudo(
    f"sh -c 'cp /etc/letsencrypt/live/{loggingHost}/* {tempCertPath}/'", hide=True
)
# is this necessary? TODO
deploymentConn.sudo(f"chmod +r {tempCertPath}/privkey.pem", hide=True)

# can log to stdout because certbot saves logs from it
print("Created temporary certificates directory on deployment server")

logConn = Connection(
    host=loggingHost,
    user=sudoUser,
    config=Config(overrides={"sudo": {"password": logCreds["sudopass"]}}),
)

sensorConns = [
    Connection(
        host=obj["host"],
        user=sudoUser,
        port=64295,
        config=Config(overrides={"sudo": {"password": obj["sudopass"]}}),
    )
    for obj in sensorCreds
]

for conn in sensorConns:
    conn.sudo("systemctl stop tpot", hide=True)

print("Stopped T-Pot on all sensor servers")

logConn.sudo("systemctl stop kibana.service", hide=True)
logConn.sudo("systemctl stop elasticsearch.service", hide=True)

print("Stopped kibana and elasticsearch on logging server")

transferSSLCerts(logConn, tempCertPath)

print("Transferred SSL certificates to logging server")

logConn.sudo("systemctl start elasticsearch.service", hide=True)
logConn.sudo("systemctl start kibana.service", hide=True)

print("Restarted elasticsearch and kibana on logging server")

for conn in sensorConns:
    transferSSLCerts(conn, tempCertPath, loggingServer=False)
    conn.sudo("systemctl start tpot", hide=True)

print("Transferred SSL certificates to all sensor servers and restarted T-Pot")

logConn.close()
for conn in sensorConns:
    conn.close()

deploymentConn.run(f"rm -rf {tempCertPath}", hide="stdout")

print("Removed temporary certificates directory on deployment server")
