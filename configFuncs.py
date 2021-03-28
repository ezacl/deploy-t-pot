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
        kibanaYml = f.read()

    kibanaYml = kibanaYml.replace("PATH_TO_FULL_CERT", pathToFullCert)
    kibanaYml = kibanaYml.replace("PATH_TO_PRIV_KEY", pathToPrivKey)
    kibanaYml = kibanaYml.replace("LOGGING_FQDN_HERE", domainName)
    kibanaYml = kibanaYml.replace("KIBANA_SYSTEM_PASSWORD", kibanaSystemPwd)

    destFile = "configFiles/kibana.yml"

    with open(destFile, "w") as f:
        f.write(kibanaYml)

    return destFile


def createLogstashConf(domainName, certPath, user, password):
    """Create logstash.conf file for sensor servers from
    configFiles/logstash.conf.template

    :domainName: FQDN of logging server
    :certPath: path to full SSL certificate on sensor server
    :user: user who has t_pot_writer elasticsearch role (usually t_pot_internal)
    :password: password to above user
    :returns: path to newly-created logstash.conf file

    """
    with open("configFiles/logstash.conf.template") as f:
        logConf = f.read()

    logConf = logConf.replace("LOGGING_FQDN_HERE", domainName)
    logConf = logConf.replace("LOGGING_CERT_PATH_HERE", certPath)
    logConf = logConf.replace("LOGGING_USER_HERE", user)
    logConf = logConf.replace("LOGGING_PASSWORD_HERE", password)

    with open("configFiles/logstash.conf", "w") as f:
        f.write(logConf)


def createUpdateCertsSh(
    loggingDomain, sensorDomains, sensorTpotUser, elasticCertsPath, kibanaPath
):
    """Create updateCerts.sh file for logging server from
    configFiles/updateCerts.sh.template

    :loggingDomain: FQDN of logging server
    :sensorDomains: list of FQDNs or IP addresses of sensor servers
    :sensorTpotUser: TODO
    :elasticCertsPath: path to elasticsearch SSL certificate directory
    :kibanaPath: path to kibana configuration directory
    :returns: path to newly-created updateCerts.sh file

    """
    with open("configFiles/updateCerts.sh.template") as f:
        updatesh = f.read()

    updatesh = updatesh.replace("SENSOR_FQDNS_OR_IPS", " ".join(sensorDomains))
    updatesh = updatesh.replace("SENSOR_TPOT_USER", sensorTpotUser)
    updatesh = updatesh.replace("LOGGING_FQDN_HERE", loggingDomain)
    updatesh = updatesh.replace("ELASTIC_CERTS_PATH", elasticCertsPath)
    updatesh = updatesh.replace("KIBANA_PATH", kibanaPath)

    destFile = "configFiles/updateCerts.sh"

    with open(destFile, "w") as f:
        f.write(updatesh)

    return destFile


def createCuratorConfigYml(loggingDomain, elasticPass):
    """Create curatorConfig.yml for logging server from
    configFiles/curatorConfig.yml.template

    :loggingDomain: FQDN of logging server
    :elasticPass: password for elastic user
    :returns: path to newly-created curatorConfig.yml file

    """
    with open("configFiles/curatorConfig.yml.template") as f:
        curatorConfig = f.read()

    curatorConfig = curatorConfig.replace("LOGGING_FQDN_HERE", loggingDomain)
    curatorConfig = curatorConfig.replace("ELASTIC_PASSWORD", elasticPass)

    destFile = "configFiles/curatorConfig.yml"

    with open(destFile, "w") as f:
        f.write(curatorConfig)

    return destFile
