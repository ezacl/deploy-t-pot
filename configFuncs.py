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
