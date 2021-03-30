import os
import secrets
import string
from zipfile import ZipFile

import requests
from requests.exceptions import HTTPError

from configFuncs import createCuratorConfigYml
from errors import BadAPIRequestError, NotCreatedError
from utils import findPassword


def createSudoUser(rootConnection, username, sudopass):
    """Create a non-root user with sudo privileges and edit SSH config file for security

    :rootConnection: fabric.Connection object with root (important) connection to server
    :username: username of new user to create
    :sudopass: sudo password for new user
    :returns: None

    """
    # add sudo user
    rootConnection.run(
        f'adduser --quiet --disabled-password --gecos "" {username}', hide="stdout"
    )
    rootConnection.run(f'echo "{username}:{sudopass}" | chpasswd', hide="stdout")
    rootConnection.run(f"usermod -aG sudo {username}", hide="stdout")
    rootConnection.run(f"mkdir /home/{username}/.ssh", hide="stdout")
    rootConnection.run(
        f"cp /root/.ssh/authorized_keys /home/{username}/.ssh/", hide="stdout"
    )
    rootConnection.run(
        f"chown -R {username}:{username} /home/{username}/.ssh", hide="stdout"
    )
    rootConnection.run(f"chmod 700 /home/{username}/.ssh", hide="stdout")

    # edit SSH config file and restart SSH service
    sshConf = "/etc/ssh/sshd_config"
    rootConnection.run(
        f"sed -i '/PasswordAuthentication\\|PermitRootLogin/d' {sshConf}",
        hide="stdout",
    )
    rootConnection.run(f'echo "PermitRootLogin no" >> {sshConf}', hide="stdout")
    rootConnection.run(f'echo "PasswordAuthentication no" >> {sshConf}', hide="stdout")
    rootConnection.run("systemctl restart sshd", hide="stdout")


def installPackages(connection, packageList):
    """Install packages on server using apt-get

    :connection: fabric.Connection object to server
    :packages: list of package names to install
    :returns: None

    """
    packageStr = " ".join(packageList)
    connection.sudo("apt-get update", hide=True)
    connection.sudo("apt-get --yes upgrade", hide=True)
    connection.sudo(f"apt-get --yes install {packageStr}", hide=True)


def generateSSLCerts(localConn, email, loggingHost, apiTokenPath):
    """Generate SSL certificates on logging server using Certbot

    :localConn: fabric.Connection object to deployment server
    :email: email address to receive Certbot notifications
    :loggingHost: domain name for logging server
    :apiTokenPath: path to digitalocean API key ini file
    :returns: path to temporary directory holding SSL certificates

    """
    certbotPackages = ["certbot", "python3-certbot-dns-digitalocean"]
    installPackages(localConn, certbotPackages)
    localConn.run(f"chmod 600 {apiTokenPath}", hide="stdout")
    localConn.sudo(
        f"certbot certonly --non-interactive --agree-tos --email {email}"
        f" --dns-digitalocean --dns-digitalocean-credentials {apiTokenPath}"
        f" -d {loggingHost}",
        hide=True,
    )

    # need to copy certs into temporary directory that doesn't need sudo access
    # in order to later transfer certs to other servers
    tempCertDir = "certs"
    localConn.run(f"mkdir {tempCertDir}", hide="stdout")
    localConn.sudo(
        f"sh -c 'cp /etc/letsencrypt/live/{loggingHost}/* {tempCertDir}/'", hide=True
    )
    localConn.sudo(f"chmod +r {tempCertDir}/privkey.pem", hide=True)

    # this has to be deleted after files are transferred for security reasons
    return tempCertDir


def transferSSLCerts(
    connection,
    certDir,
    loggingServer=True,
    elasticPath=None,
    elasticCertsPath=None,
    kibanaPath=None,
    kibanaCertsPath=None,
    dataPath=None,
):
    """Transfer SSL certificates to either logging or sensor server

    :connection: fabric.Connection object to logging or sensor server
    :certDir: path to temporary directory containing SSL certificates
    :loggingServer: optional, whether transferring SSL certificates to the logging
    server or to a sensor server. Defaults to True
    :elasticPath: optional, path to elasticsearch configuration directory
    (logging server)
    :elasticCertsPath: optional, path to elasticsearch SSL certificate
    directory (logging server)
    :kibanaPath: optional, path to kibana configuration directory (logging server)
    :kibanaCertsPath: optional, path to kibana SSL certificate directory
    (logging server)
    :dataPath: optional, path to elk data directory (sensor server)
    :returns: None

    """
    if loggingServer:
        connection.run("mkdir certs", hide="stdout")

        for file in os.listdir(certDir):
            connection.put(f"{certDir}/{file}", remote="certs/")

        connection.sudo(f"rm -rf {elasticCertsPath}", hide=True)
        connection.sudo(f"mv certs {elasticPath}/", hide=True)
        connection.sudo(f"chown -R root:elasticsearch {elasticCertsPath}", hide=True)
        connection.sudo(f"chmod 644 {elasticCertsPath}/privkey.pem", hide=True)
        connection.sudo(f"rm -rf {kibanaCertsPath}", hide=True)
        connection.sudo(f"cp -r {elasticCertsPath} {kibanaPath}/", hide=True)
    else:
        # if need to transfer certs to sensor server
        connection.put(f"{certDir}/fullchain.pem")
        connection.sudo(f"mv fullchain.pem {dataPath}/", hide=True)


def setupCurator(connection, configPath, elasticPass):
    """Set up elasticsearch-curator service to delete old elasticsearch indices

    :connection: fabric.Connection object to logging server
    :configPath: path to curator configuration directory
    :elasticPass: password for user elastic
    :returns: None

    """
    # commands to set up elasticsearch-curator to delete old indices
    connection.sudo("mkdir /var/log/curator", hide=True)

    curatorConfigPath = createCuratorConfigYml(connection.host, elasticPass)
    connection.put(curatorConfigPath)
    connection.put("configFiles/curatorActions.yml")
    connection.sudo(f"mv curatorConfig.yml curatorActions.yml {configPath}", hide=True)

    # add cronjob to run curator every day at midnight (curator needs root)
    curatorCommand = (
        f"0 0 * * * root curator --config {configPath}curatorConfig.yml"
        f" {configPath}curatorActions.yml"
    )
    connection.sudo(f"sh -c 'echo \"{curatorCommand}\" >> /etc/crontab'", hide=True)


def createTPotRole(hostPort, creatorUser, creatorPwd):
    """Create t_pot_writer elasticsearch role for sensor servers with correct
    permissions to send honeypot data to logging server

    :hostPort: elasticsearch FQDN and port, in form FQDN:port
    :creatorUser: user with which to make API requests (usually elastic)
    :creatorPwd: password to above user
    :returns: name of role created

    """
    roleName = "t_pot_writer"

    # permissions needed to send honeypot data
    roleData = {
        "cluster": [
            "manage_index_templates",
            "monitor",
        ],
        "indices": [
            {
                "names": [
                    "logstash-*",
                ],
                "privileges": [
                    "write",
                    "delete",
                    "create_index",
                ],
                "allow_restricted_indices": False,
            }
        ],
        "applications": [],
        "run_as": [],
        "metadata": {},
        "transient_metadata": {
            "enabled": True,
        },
    }

    roleResp = requests.post(
        f"https://{hostPort}/_security/role/{roleName}",
        auth=(creatorUser, creatorPwd),
        json=roleData,
    )

    try:
        roleResp.raise_for_status()
    except HTTPError:
        # Usually if API request is made before elasticsearch service is ready
        raise BadAPIRequestError(
            f"{roleResp.text}\nBad API request. See response above."
        )

    # creating the same role twice will not change anything
    if not roleResp.json()["role"]["created"]:
        raise NotCreatedError(f"{roleName} role not created. Does it already exist?")

    return roleName


def createTPotUser(hostPort, creatorUser, creatorPwd=None, createdPwd=None):
    """Create t_pot_internal elasticsearch user for sensor servers
    with t_pot_writer role

    :hostPort: elasticsearch FQDN and port, in form FQDN:port
    :creatorUser: user with which to make API requests (usually elastic)
    :creatorPwd: optional, password to above user. If left blank, will try to look in
    passwords.txt
    :createdPwd: optional, password for t_pot_internal user to be created. If left
    blank, will generate a random password
    :returns: name of created user and corresponding password

    """
    if creatorPwd is None:
        # try to find user password in text file if password not specified
        with open("passwords.txt") as f:
            creatorPwd = findPassword(f.read(), creatorUser)

    userName = "t_pot_internal"
    # first create role to assign to user
    roleName = createTPotRole(hostPort, creatorUser, creatorPwd)

    # generate random password if none specified
    if createdPwd is None:
        createdPwd = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(20)
        )

    userData = {
        "roles": [
            roleName,
        ],
        "password": createdPwd,
        "full_name": "",
        "email": "",
        "metadata": {},
        "enabled": True,
    }

    userResp = requests.post(
        f"https://{hostPort}/_security/user/{userName}",
        auth=(creatorUser, creatorPwd),
        json=userData,
    )

    try:
        userResp.raise_for_status()
    except HTTPError:
        # Usually if API request is made before elasticsearch service is ready
        raise BadAPIRequestError(
            f"{userResp.text}\nBad API request. See response above."
        )

    # creating the same user twice will not change anything
    if not userResp.json()["created"]:
        raise NotCreatedError(f"{userName} user not created. Does it already exist?")

    return userName, createdPwd


def importKibanaObjects(hostPort, userName, password):
    """Convenience function to programmatically import nice T-Pot attack visualizations
    in kibana as well as set dark mode. Note that the /api/saved_objects/_import
    endpoint is experimental in ELK 7.11, so this may not work with future versions.

    :hostPort: elasticsearch FQDN and port, in form FQDN:port
    :userName: user with which to make API requests (usually elastic)
    :password: password to above user
    :returns: None

    """
    # get kibana_export.ndjson from tpotce-light repository
    zipResp = requests.get(
        "https://raw.githubusercontent.com/ezacl/tpotce-light/"
        "master/etc/objects/kibana_export.ndjson.zip"
    )
    zipResp.raise_for_status()

    zipName = "kibanaObjects.zip"

    with open(zipName, "wb") as f:
        f.write(zipResp.content)

    # extract .ndjson file from zip
    with ZipFile(zipName) as zf:
        zf.extractall()
        objectFile = zf.namelist()[0]

    objFileHandle = open(objectFile)
    importFile = {"file": objFileHandle}

    authTup = (userName, password)
    headers = {"kbn-xsrf": "true"}

    # import all objects in file through API
    importResp = requests.post(
        f"https://{hostPort}/api/saved_objects/_import",
        params={"overwrite": "true"},
        headers=headers,
        auth=authTup,
        files=importFile,
    )

    objFileHandle.close()
    os.remove(zipName)
    os.remove(objectFile)

    try:
        importResp.raise_for_status()
    except HTTPError:
        # Usually if API request is made before kibana service is ready
        raise BadAPIRequestError(
            f"{importResp.text}\nBad API request. See response above."
        )

    # enable kibaana dark mode
    darkModeResp = requests.post(
        f"https://{hostPort}/api/kibana/settings/theme:darkMode",
        headers=headers,
        auth=authTup,
        data={"value": "true"},
    )

    try:
        darkModeResp.raise_for_status()
    except HTTPError:
        # Usually if API request is made before kibana service is ready
        raise BadAPIRequestError(
            f"{darkModeResp.text}\nBad API request. See response above."
        )
