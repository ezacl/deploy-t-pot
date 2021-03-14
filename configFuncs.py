import secrets
import string
from pprint import pprint

import requests
from requests.exceptions import HTTPError

from utils import findPassword


def createElasticsearchYml(pathToPrivKey, pathToHostCert, pathToFullCert):
    """TODO: Docstring for createElasticsearchYml.

    :pathToPrivKey: TODO
    :pathToHostCert: TODO
    :pathToFullCert: TODO
    :returns: TODO

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
    """TODO: Docstring for createKibanaYml.

    :ipAddress: TODO
    :kibanaSystemPwd: TODO
    :pathToPrivKey: TODO
    :pathToFullCert: TODO
    :returns: TODO

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


def createLogstashConf(domain, certPath, user, password):
    """TODO: Docstring for createLogstashConf.

    :domain: TODO
    :certPath: TODO
    :user: TODO
    :password: TODO
    :returns: TODO

    """
    with open("configFiles/logstash.conf.template") as f:
        logConf = f.read()

    logConf = logConf.replace("LOGGING_FQDN_HERE", domain)
    logConf = logConf.replace("LOGGING_CERT_PATH_HERE", certPath)
    logConf = logConf.replace("LOGGING_USER_HERE", user)
    logConf = logConf.replace("LOGGING_PASSWORD_HERE", password)

    with open("configFiles/logstash.conf", "w") as f:
        f.write(logConf)


def createTPotRole(hostPort, creatorUser, creatorPwd):
    """TODO: Docstring for createTPotRole.

    :hostPort: TODO
    :creatorUser: TODO
    :creatorPwd: TODO
    :returns: TODO

    """
    roleName = "t_pot_writer"

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
        pprint(roleResp.json())
        raise Exception("Bad API request. See response above.")

    if not roleResp.json()["role"]["created"]:
        raise Exception(f"{roleName} role not created. Does it already exist?")

    return roleName


def createTPotUser(hostPort, creatorUser, creatorPwd=None, createdPwd=None):
    """TODO: Docstring for createTPotUser.

    :hostPort: TODO
    :creatorUser: TODO
    :creatorPwd: TODO
    :createdPwd: TODO
    :returns: TODO

    """
    if creatorPwd is None:
        # try to find user password in text file if password not specified
        with open("passwords.txt") as f:
            creatorPwd = findPassword(f.read(), creatorUser)

    userName = "t_pot_internal"
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
        pprint(userResp.json())
        raise Exception("Bad API request. See response above.")

    if not userResp.json()["created"]:
        raise Exception(f"{userName} user not created. Does it already exist?")

    return userName, createdPwd


def importKibanaObjects(hostPort, userName, password, objectFile):
    """TODO: Docstring for importKibanaObjects.

    :hostPort: TODO
    :userName: TODO
    :password: TODO
    :objectFile: TODO
    :returns: TODO

    """
    importFile = {"file": open(objectFile)}
    authTup = (userName, password)

    importResp = requests.post(
        f"https://{hostPort}/api/saved_objects/_import",
        params={"overwrite": "true"},
        headers={"kbn-xsrf": "true"},
        auth=authTup,
        files=importFile,
    )

    try:
        importResp.raise_for_status()
    except HTTPError:
        print(importResp.text)
        raise Exception("Bad API request. See response above.")
