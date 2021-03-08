def createElasticsearchYml(pathToKey, pathToCrt, pathToCaCrt):
    """TODO: Docstring for createElasticsearchYml.

    :pathToKey: TODO
    :pathToCrt: TODO
    :pathToCaCrt: TODO
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
xpack.security.transport.ssl.key: {pathToKey}
xpack.security.transport.ssl.certificate: {pathToCrt}
xpack.security.transport.ssl.certificate_authorities: [ \\"{pathToCaCrt}\\" ]

# client to node communication

xpack.security.http.ssl.enabled: true
xpack.security.http.ssl.verification_mode: certificate
xpack.security.http.ssl.key: {pathToKey}
xpack.security.http.ssl.certificate: {pathToCrt}
xpack.security.http.ssl.certificate_authorities: [ \\"{pathToCaCrt}\\" ]

# Workaround for logstash error Encountered a retryable error. Will retry with exponential backoff

http.max_content_length: 1gb"""

    return configurationOptions


def createKibanaYml(ipAddress, kibanaPwd, pathToKey, pathToCrt, pathToCaCrt):
    """TODO: Docstring for createKibanaYml.

    :ipAddress: TODO
    :kibanaPwd: TODO
    :pathToKey: TODO
    :pathToCrt: TODO
    :pathToCaCrt: TODO
    :returns: TODO

    """

    configurationOptions = f"""
# T-Pot Distributed Options
server.port: 5601
server.host: \\"0.0.0.0\\"
elasticsearch.hosts: [\\"https://{ipAddress}:64298\\"]
elasticsearch.username: \\"kibana\\"
elasticsearch.password: \\"{kibanaPwd}\\"
elasticsearch.ssl.certificate: {pathToCrt}
elasticsearch.ssl.key: {pathToKey}
elasticsearch.ssl.certificateAuthorities: [\\"{pathToCaCrt}\\"]"""

    return configurationOptions
