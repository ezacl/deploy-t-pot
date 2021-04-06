import time
from datetime import datetime

import requests

from utils import splitDomain

KEY_BASE_NAME = "T-Pot deployment"
DEFAULT_REGION = "nyc1"


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
    it has an IP address associated to it) and return IP address

    :apiToken: DigitalOcean API key
    :dropletId: ID of droplet
    :returns: IPv4 address of droplet

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
    date = datetime.now().strftime("%m-%d-%Y")
    sshKeyName = f"{KEY_BASE_NAME} {date}"
    sshKeyId = addSSHKey(apiToken, sshKeyName, sshKey)

    region = chooseRegion(apiToken, DEFAULT_REGION)

    subDomain, domainName = splitDomain(loggingObj["host"])
    createVM(apiToken, subDomain, domainName, region, sshKeyId, loggerSize=True)

    for sensor in sensorObjs:
        subDomain, domainName = splitDomain(sensor["host"])
        createVM(apiToken, subDomain, domainName, region, sshKeyId)


def deleteSSHKey(apiToken):
    """Delete T-Pot SSH key through DigitalOcean API

    :apiToken: DigitalOcean API key
    :returns: None

    """
    sshEndpoint = "https://api.digitalocean.com/v2/account/keys"
    headers = {"Authorization": f"Bearer {apiToken}"}
    sshReq = requests.get(sshEndpoint, headers=headers)
    sshReq.raise_for_status()

    # delete deployment server SSH key
    for key in sshReq.json()["ssh_keys"]:
        if key["name"].startswith(KEY_BASE_NAME):
            deleteKeyId = key["id"]
            sshDeleteReq = requests.delete(
                f"{sshEndpoint}/{deleteKeyId}", headers=headers
            )
            sshDeleteReq.raise_for_status()


def deleteDNSRecords(apiToken, tldList, subdomainList):
    """Delete T-Pot DNS records through DigitalOcean API

    :apiToken: DigitalOcean API key
    :tldList: list of all top-level domain names involved in T-Pot network
    :subdomainList: list of all subdomains involved in T-Pot network
    :returns: None

    """
    headers = {"Authorization": f"Bearer {apiToken}"}
    recordsList = []

    # make list of all records across all domains
    for domainName in tldList:
        domainEndpoint = f"https://api.digitalocean.com/v2/domains/{domainName}/records"
        recordReq = requests.get(domainEndpoint, headers=headers)
        recordReq.raise_for_status()

        # add top-level domain to each record to know how to delete it later
        for record in recordReq.json()["domain_records"]:
            # "domain" key isn't returned by API, so add it for use in next for loop
            record["domain"] = domainName
            recordsList.append(record)

    # delete all T-Pot DNS records
    for record in recordsList:
        if record["name"] in subdomainList:
            domainName = record["domain"]
            recordId = record["id"]
            domainEndpoint = (
                "https://api.digitalocean.com/v2/domains/"
                f"{domainName}/records/{recordId}"
            )
            recordDeleteReq = requests.delete(domainEndpoint, headers=headers)
            recordDeleteReq.raise_for_status()


def deleteDroplets(apiToken, subdomainList):
    """Delete all T-Pot related droplets through DigitalOcean API

    :apiToken: DigitalOcean API key
    :subdomainList: list of all subdomains involved in T-Pot network
    :returns: None

    """
    headers = {"Authorization": f"Bearer {apiToken}"}
    dropletEndpoint = "https://api.digitalocean.com/v2/droplets"
    dropletReq = requests.get(dropletEndpoint, headers=headers)
    dropletReq.raise_for_status()

    # delete all T-Pot droplets
    for droplet in dropletReq.json()["droplets"]:
        # installation scripts automatically name all droplets the subdomain chosen for
        # each server in credentials.json, so rely on that to identify them
        if droplet["name"] in subdomainList:
            dropletId = droplet["id"]
            dropletDeleteReq = requests.delete(
                f"{dropletEndpoint}/{dropletId}", headers=headers
            )
            dropletDeleteReq.raise_for_status()


def APIRemoveNetwork(apiToken, loggingObj, sensorObjs):
    """Cleanly tear down all droplets/DNS records/SSH keys associated with T-Pot network
    through DigitalOcean API

    :apiToken: DigitalOcean API key
    :loggingObj: JSON object representing logging server
    :sensorObjs: array of JSON objects representing sensor servers
    :returns: None

    """
    subdomainList = []
    tldList = []

    # get all subdomains and top-level domains involved in T-Pot network
    for serverObj in [loggingObj] + sensorObjs:
        subDomain, domainName = splitDomain(serverObj["host"])
        subdomainList.append(subDomain)
        tldList.append(domainName)

    # remove duplicate top-level domains
    tldList = list(set(tldList))

    deleteSSHKey(apiToken)

    deleteDNSRecords(apiToken, tldList, subdomainList)

    deleteDroplets(apiToken, subdomainList)
