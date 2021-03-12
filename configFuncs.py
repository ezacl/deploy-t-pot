from pprint import pprint

import requests
from requests.exceptions import HTTPError


def createElasticsearchYml(pathToPrivKey, pathToHostCert, pathToFullCert):
    """TODO: Docstring for createElasticsearchYml.

    :pathToPrivKey: TODO
    :pathToHostCert: TODO
    :pathToFullCert: TODO
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
xpack.security.transport.ssl.key: {pathToPrivKey}
xpack.security.transport.ssl.certificate: {pathToHostCert}
xpack.security.transport.ssl.certificate_authorities: [ \\"{pathToFullCert}\\" ]

# client to node communication

xpack.security.http.ssl.enabled: true
xpack.security.http.ssl.verification_mode: certificate
xpack.security.http.ssl.key: {pathToPrivKey}
xpack.security.http.ssl.certificate: {pathToFullCert}

# Workaround for logstash error Encountered a retryable error. Will retry with exponential backoff

http.max_content_length: 1gb"""

    return configurationOptions


def createKibanaYml(ipAddress, kibanaSystemPwd, pathToPrivKey, pathToHostCert):
    """TODO: Docstring for createKibanaYml.

    :ipAddress: TODO
    :kibanaSystemPwd: TODO
    :pathToPrivKey: TODO
    :pathToHostCert: TODO
    :returns: TODO

    """

    configurationOptions = f"""
# T-Pot Distributed Options

server.port: 5601
server.host: \\"0.0.0.0\\"

server.ssl.enabled: true
server.ssl.certificate: {pathToHostCert}
server.ssl.key: {pathToPrivKey}

elasticsearch.hosts: [\\"https://{ipAddress}:64298\\"]
elasticsearch.username: \\"kibana_system\\"
elasticsearch.password: \\"{kibanaSystemPwd}\\\""""

    return configurationOptions


def createTPotRole(hostPort, user, password):
    """TODO: Docstring for createTPotRole.

    :hostPort: TODO
    :user: TODO
    :password: TODO
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
        auth=(user, password),
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


def createTPotUser(hostPort, user, password, roleName, userPass):
    """TODO: Docstring for createTPotUser.

    :hostPort: TODO
    :user: TODO
    :password: TODO
    :roleName: TODO
    :roleName: TODO
    :returns: TODO

    """
    userName = "t_pot_internal"

    userData = {
        "roles": [
            roleName,
        ],
        "password": userPass,
        "full_name": "",
        "email": "",
        "metadata": {},
        "enabled": True,
    }

    userResp = requests.post(
        f"https://{hostPort}/_security/user/{userName}",
        auth=(user, password),
        json=userData,
    )

    try:
        userResp.raise_for_status()
    except HTTPError:
        pprint(userResp.json())
        raise Exception("Bad API request. See response above.")

    if not userResp.json()["created"]:
        raise Exception(f"{userName} user not created. Does it already exist?")

    return userName
