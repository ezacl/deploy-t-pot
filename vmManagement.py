import time

import requests


def addSSHKey(apiToken, keyName, keyContent):
    """Add SSH public key to DigitalOcean account and return its ID

    :apiToken: DigitalOcean API key
    :keyName: Name chosen for SSH key
    :keyContent: content of the public key (copy and paste the .pub file)
    :returns: the SSH key's ID for future use

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
    """Create DNS A record connection a specific domain name to an IP address

    :apiToken: DigitalOcean API key
    :subDomain: subdomain for A record (if FQDN is subdomain.domain.com, this is
    subdomain)
    :domainName: top-level domain for A record (if FQDN is subdomain.domain.com, this
    is domain)
    :ipAddress: IP address for A record
    :returns: None

    """
    endpoint = f"https://api.digitalocean.com/v2/domains/{domainName}/records"
    headers = {"Authorization": f"Bearer {apiToken}"}
    recordData = {"type": "A", "name": subDomain, "data": ipAddress, "ttl": 3600}
    recordReq = requests.post(endpoint, json=recordData, headers=headers)
    recordReq.raise_for_status()


def waitForVM(apiToken, dropletId):
    """Block until DigitalOcean droplet (created by createVM) is up and running (until
    it has an IP address associated to it)

    :apiToken: DigitalOcean API key
    :dropletId: ID of droplet
    :returns: None

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
    """Create DigitalOcean droplet with associated DNS A record

    :apiToken: DigitalOcean API key
    :name: chosen name for droplet and subdomain for DNS record
    :domainName: top-level domain name for DNS record
    :region: chosen region for droplet (such as "nyc1", etc.)
    :sshKeyId: ID of SSH key to add to droplet (returned by addSSHKey)
    :loggerSize: size slug of droplet (such as "s-4vcpu-8gb", etc.)
    :returns: None

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


def chooseRegion(apiToken, defaultRegion):
    """Return most frequent previous droplet region to use for network servers

    :apiToken: DigitalOcean API key
    :defaultRegion: Region to fall back to if no currently active droplets
    :returns: most frequent droplet region slug used for all current droplets

    """
    endpoint = "https://api.digitalocean.com/v2/droplets"
    headers = {"Authorization": f"Bearer {apiToken}"}
    dropletReq = requests.get(endpoint, headers=headers)
    dropletReq.raise_for_status()
    jsonResp = dropletReq.json()

    regionList = [droplet["region"]["slug"] for droplet in jsonResp["droplets"]]

    # return most frequent element in regionList, else defaultRegion if regionList is
    # empty
    try:
        return max(set(regionList), key=regionList.count)
    except ValueError:
        return defaultRegion


def createAllVMs(apiToken, loggingObj, sensorObjs, sshKey):
    """Create multiple DigitalOcean droplets from JSON objects in credentials.json

    :apiToken: DigitalOcean API key
    :loggingObj: JSON object representing logging server
    :sensorObjs: array of JSON objects representing sensor servers
    :sshKey: contents of SSH public key to add to each server
    :returns: None

    """
    sshKeyName = "T-Pot deployment server"
    sshKeyId = addSSHKey(apiToken, sshKeyName, sshKey)

    defaultRegion = "nyc1"
    region = chooseRegion(apiToken, defaultRegion)

    def splitDomain(domainStr):
        """Split an FQDN as a string into its domain and subdomain"""
        splitStr = domainStr.split(".")
        return ".".join(splitStr[:-2]), ".".join(splitStr[-2:])

    subDomain, domainName = splitDomain(loggingObj["host"])
    createVM(apiToken, subDomain, domainName, region, sshKeyId, loggerSize=True)

    for sensor in sensorObjs:
        subDomain, domainName = splitDomain(sensor["host"])
        createVM(apiToken, subDomain, domainName, region, sshKeyId)
