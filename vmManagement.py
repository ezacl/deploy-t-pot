import time

import requests


def addSSHKey(apiToken, keyName, keyContent):
    """TODO: Docstring for addSSHKey.

    :apiToken: TODO
    :keyName: TODO
    :keyContent: TODO
    :returns: TODO

    """
    endpoint = "https://api.digitalocean.com/v2/account/keys"
    headers = {"Authorization": f"Bearer {apiToken}"}
    keyData = {"name": keyName, "public_key": keyContent}
    sshReq = requests.post(endpoint, json=keyData, headers=headers)
    sshReq.raise_for_status()

    jsonResp = sshReq.json()

    # need ID to create new droplet with SSH key
    return jsonResp["ssh_key"]["id"]


def createARecord(apiToken, subDomain, domainName, ipAddress):
    """TODO: Docstring for createARecord.

    :apiToken: TODO
    :subDomain: TODO
    :domainName: TODO
    :ipAddress: TODO
    :returns: TODO

    """
    endpoint = f"https://api.digitalocean.com/v2/domains/{domainName}/records"
    headers = {"Authorization": f"Bearer {apiToken}"}
    recordData = {"type": "A", "name": subDomain, "data": ipAddress, "ttl": 3600}
    recordReq = requests.post(endpoint, json=recordData, headers=headers)
    recordReq.raise_for_status()


def waitForVM(apiToken, dropletId):
    """TODO: Docstring for waitForVM.

    :apiToken: TODO
    :dropletId: TODO
    :returns: TODO

    """
    endpoint = f"https://api.digitalocean.com/v2/droplets/{dropletId}"
    headers = {"Authorization": f"Bearer {apiToken}"}

    while True:
        time.sleep(5)
        dropletReq = requests.get(endpoint, headers=headers)
        try:
            for ipInfo in dropletReq.json()["droplet"]["networks"]["v4"]:
                if ipInfo["type"] == "public":
                    return ipInfo["ip_address"]
        except KeyError:
            pass


def createVM(apiToken, name, domainName, region, sshKeyId, loggerSize=False):
    """TODO: Docstring for createVM.

    :apiToken: TODO
    :name: TODO
    :domainName: TODO
    :region: TODO
    :sshKeyId: TODO
    :loggerSize: TODO
    :returns: TODO

    """
    endpoint = "https://api.digitalocean.com/v2/droplets"
    headers = {"Authorization": f"Bearer {apiToken}"}

    size = "s-4vcpu-8gb" if loggerSize else "s-2vcpu-4gb"

    dropletData = {
        "name": name,
        "region": region,
        "size": size,
        "image": "debian-10-x64",
        "ssh_keys": [sshKeyId],
    }
    dropletReq = requests.post(endpoint, json=dropletData, headers=headers)
    dropletReq.raise_for_status()

    dropletId = dropletReq.json()["droplet"]["id"]

    ipAddress = waitForVM(apiToken, dropletId)

    createARecord(apiToken, name, domainName, ipAddress)


def createAllVMs(apiToken, loggingObj, sensorObjs, sshKey):
    """TODO: Docstring for createAllVMs.

    :apiToken: TODO
    :loggingObj: TODO
    :sensorObjs: TODO
    :sshKey: TODO
    :returns: TODO

    """
    sshKeyName = "T-Pot deployment server"
    sshKeyId = addSSHKey(apiToken, sshKeyName, sshKey)

    defaultRegion = "nyc1"

    subDomain = ".".join(loggingObj["host"].split(".")[:-2])
    domainName = ".".join(loggingObj["host"].split(".")[-2:])
    createVM(apiToken, subDomain, domainName, defaultRegion, sshKeyId, loggerSize=True)

    for sensor in sensorObjs:
        subDomain = ".".join(sensor["host"].split(".")[:-2])
        domainName = ".".join(sensor["host"].split(".")[-2:])
        createVM(apiToken, subDomain, domainName, defaultRegion, sshKeyId)
