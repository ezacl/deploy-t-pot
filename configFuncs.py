import os
import secrets
import string
from zipfile import ZipFile

import requests
from requests.exceptions import HTTPError

from errors import BadAPIRequestError, NotCreatedError
from utils import findPassword


def createElasticsearchYml(pathToPrivKey, pathToHostCert, pathToFullCert):
    """Create elasticsearch.yml file for logging server from
    configFiles/elasticsearch.yml.template

    :pathToPrivKey: path to SSL private key on logging server
    :pathToHostCert: path to host SSL certificate on logging server
    :pathToFullCert: path to full SSL certificate on logging server
    :returns: path to newly-created elasticsearch.yml file

    """
    with open("configFiles/elasticsearch.yml.template") as f:
        elasticYml = f.read()

    elasticYml = elasticYml.replace("PATH_TO_PRIV_KEY", pathToPrivKey)
    elasticYml = elasticYml.replace("PATH_TO_HOST_CERT", pathToHostCert)
    elasticYml = elasticYml.replace("PATH_TO_FULL_CERT", pathToFullCert)

    destFile = "configFiles/elasticsearch.yml"

    with open(destFile, "w") as f:
        f.write(elasticYml)

    return destFile


def createKibanaYml(domainName, kibanaSystemPwd, pathToPrivKey, pathToFullCert):
    """Create kibana.yml file for logging server from configFiles/kibana.yml.template

    :domainName: FQDN of logging server
    :kibanaSystemPwd: password to kibana_system user (created by
    elasticsearch-setup-passwords)
    :pathToPrivKey: path to SSL private key on logging server
    :pathToFullCert: path to full SSL certificate on logging server
    :returns: path to newly-created kibana.yml file

    """
    with open("configFiles/kibana.yml.template") as f:
        elasticYml = f.read()

    elasticYml = elasticYml.replace("PATH_TO_FULL_CERT", pathToFullCert)
    elasticYml = elasticYml.replace("PATH_TO_PRIV_KEY", pathToPrivKey)
    elasticYml = elasticYml.replace("LOGGING_FQDN_HERE", domainName)
    elasticYml = elasticYml.replace("KIBANA_SYSTEM_PASSWORD", kibanaSystemPwd)

    destFile = "configFiles/kibana.yml"

    with open(destFile, "w") as f:
        f.write(elasticYml)

    return destFile


def createLogstashConf(domainName, certPath, user, password):
    """Create logstash.conf file for sensor servers from
    configFiles/logstash.conf.template

    :domainName: FQDN of logging server
    :certPath: path to full SSL certificate on sensor server
    :user: user who has t_pot_writer elasticsearch role (usually t_pot_internal)
    :password: password to above user
    :returns: None

    """
    with open("configFiles/logstash.conf.template") as f:
        logConf = f.read()

    logConf = logConf.replace("LOGGING_FQDN_HERE", domainName)
    logConf = logConf.replace("LOGGING_CERT_PATH_HERE", certPath)
    logConf = logConf.replace("LOGGING_USER_HERE", user)
    logConf = logConf.replace("LOGGING_PASSWORD_HERE", password)

    with open("configFiles/logstash.conf", "w") as f:
        f.write(logConf)


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

    importFile = {"file": open(objectFile)}

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
