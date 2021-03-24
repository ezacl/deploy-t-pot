import os
import secrets
import string
from zipfile import ZipFile

import requests
from requests.exceptions import HTTPError

from errors import BadAPIRequestError, NotCreatedError
from utils import createCuratorConfigYml, findPassword


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
        print(roleResp.text)
        raise BadAPIRequestError("Bad API request. See response above.")

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

        print(f"Password for user {userName}: {createdPwd}")

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
        print(userResp.text)
        raise BadAPIRequestError("Bad API request. See response above.")

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
        print(importResp.text)
        raise BadAPIRequestError("Bad API request. See response above.")

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
        print(darkModeResp.text)
        raise BadAPIRequestError("Bad API request. See response above.")
