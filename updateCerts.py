import json

from fabric import Config, Connection
from invoke.config import Config as InvokeConfig
from invoke.context import Context

from deploymentHelpers import transferSSLCerts

# WRITE A BASH WRAPPER TO RUN THIS BUT MAKE SURE IT CDS INTO THIS DIRECTORY FIRST TODO

credsFile = "credentials.json"
# don't hardcode this TODO
sudoUser = "tpotadmin"

with open(credsFile) as f:
    credentials = json.load(f)
    deploymentCreds = credentials["deployment"]
    logCreds = credentials["logging"]
    sensorCreds = credentials["sensors"]

loggingHost = logCreds["host"]

# can I assume that the deployment server sudo user will run this? Won't it be root? TODO
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

for conn in sensorConns:
    transferSSLCerts(conn, tempCertPath, loggingServer=False)
    conn.sudo("systemctl start tpot", hide=True)

print("Transferred SSL certificates to all sensor servers")

logConn.sudo("systemctl start elasticsearch.service", hide=True)
logConn.sudo("systemctl start kibana.service", hide=True)

print("Restarted elasticsearch and kibana on logging server")

logConn.close()
for conn in sensorConns:
    conn.close()

deploymentConn.run(f"rm -rf {tempCertPath}", hide="stdout")

print("Removed temporary certificates directory on deployment server")
