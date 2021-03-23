from utils import createCuratorConfigYml


def installPackages(connection, packageList):
    """TODO: Docstring for installPackages.

    :connection: TODO
    :packages: TODO
    :returns: TODO

    """
    packageStr = " ".join(packageList)
    connection.run("apt-get update && apt-get --yes upgrade", pty=True, hide="stdout")
    connection.run(
        f"apt-get --yes install {packageStr}",
        pty=True,
        hide="stdout",
    )


def generateSSLCerts(connection, email, elasticCertsPath, kibanaCertsPath):
    """TODO: Docstring for generateSSLCerts.

    :connection: TODO
    :email: TODO
    :elasticCertsPath: TODO
    :kibanaCertsPath: TODO
    :returns: TODO

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
    """TODO: Docstring for setupCurator.

    :connection: TODO
    :configPath: TODO
    :elasticPass: TODO
    :returns: TODO

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
