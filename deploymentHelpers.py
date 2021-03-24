from utils import createCuratorConfigYml


def installPackages(connection, packageList):
    """Install packages on server using apt-get

    :connection: fabric.Connection object to server
    :packages: list of package names to install
    :returns: None

    """
    packageStr = " ".join(packageList)
    connection.run("apt-get update && apt-get --yes upgrade", pty=True, hide="stdout")
    connection.run(
        f"apt-get --yes install {packageStr}",
        pty=True,
        hide="stdout",
    )


def generateSSLCerts(connection, email, elasticCertsPath, kibanaCertsPath):
    """Generate SSL certificates on logging server using Certbot

    :connection: fabric.Connection object to logging server
    :email: email address to receive Certbot notifications
    :elasticCertsPath: path to elasticsearch SSL certificate directory
    :kibanaCertsPath: path to kibana SSL certificate directory
    :returns: None

    """
    connection.run(f"mkdir {elasticCertsPath}", hide="stdout")
    connection.run(f"mkdir {kibanaCertsPath}", hide="stdout")

    connection.run(
        f"certbot certonly --standalone -d {connection.host} --non-interactive"
        f" --agree-tos --email {email}",
        hide="stdout",
    )

    # tried to symlink these instead, but kept on getting permission errors in ES logs
    connection.run(
        f"cp /etc/letsencrypt/live/{connection.host}/* {elasticCertsPath}/",
        hide="stdout",
    )
    connection.run(f"chmod 644 {elasticCertsPath}/privkey.pem", hide="stdout")

    # copying certificates isn't good but I couldn't get it to work with symlinks
    connection.run(f"cp {elasticCertsPath}/* {kibanaCertsPath}/", hide="stdout")


def setupCurator(connection, configPath, elasticPass):
    """Set up elasticsearch-curator service to delete old elasticsearch indices

    :connection: fabric.Connection object to logging server
    :configPath: path to curator configuration directory
    :elasticPass: password for user elastic
    :returns: None

    """
    # commands to set up elasticsearch-curator to delete old indices
    connection.run("mkdir /var/log/curator", hide="stdout")

    curatorConfigPath = createCuratorConfigYml(connection.host, elasticPass)
    connection.put(curatorConfigPath, remote=configPath)
    connection.put("configFiles/curatorActions.yml", remote=configPath)

    # add cronjob to run curator every day at midnight
    curatorCommand = (
        f"curator --config {configPath}curatorConfig.yml"
        f" {configPath}curatorActions.yml"
    )
    connection.run(f'echo "{curatorCommand}" >> /etc/crontab')
