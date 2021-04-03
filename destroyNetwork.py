import json

from errors import NoCredentialsFileError
from vmManagement import APIRemoveNetwork


def destroyNetwork(credsFile="credentials.json", DOApiKeyFile="digitalocean.ini"):
    """Automatically and completely tear down T-Pot network through DigitalOcean API

    :credsFile: optional, path to credentials JSON file. Defaults to credentials.json
    :DOApiKeyFile: optional, path to file containing DigitalOcean API key. Defaults to
    digitalocean.ini
    :returns: None

    """
    try:
        # get server credentials from credentials file
        with open(credsFile) as f:
            credentials = json.load(f)
            logCreds = credentials["logging"]
            sensorCreds = credentials["sensors"]
    except FileNotFoundError:
        raise NoCredentialsFileError(
            f"{credsFile} not found. Did you copy credentials.json.template?"
        )

    # get DigitalOcean API key
    with open(DOApiKeyFile) as f:
        apiKey = f.read().strip().split()[-1]

    APIRemoveNetwork(apiKey, logCreds, sensorCreds)

    print("T-Pot network successfully destroyed.")


if __name__ == "__main__":
    destroyNetwork()
