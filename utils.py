import re
import time

import requests
from requests.exceptions import ConnectionError

from errors import NoSubdomainError, NotFoundError


def findPassword(passwordText, username):
    """Find specified password in text returned by elasticsearch-setup-passwords command

    :passwordText: text returned by elasticsearch-setup-passwords as a string
    :username: username for which to find corresponding password
    :returns: corresponding password as a string

    """
    try:
        pwdSearch = rf"(PASSWORD {username} = )(\S+)"
        pwdRegex = re.compile(pwdSearch)
        pwdMatch = pwdRegex.search(passwordText)

        return pwdMatch.group(2)
    except AttributeError:
        # if pattern not found, pwdMatch will be None, raising AttributeError
        raise NotFoundError(f"{username} password not found in text.")


def waitForService(host, port):
    """Simple function to block until the specified port on host opens up

    :host: host of port to check as an FQDN (usually fabric.Connection.host)
    :port: port number to check availability of
    :returns: None

    """
    status = 600

    # wait until server responds with < 500 status code to consider it "ready"
    while status >= 500:
        try:
            resp = requests.get(f"https://{host}:{port}")
            status = resp.status_code
        except ConnectionError:
            pass

        time.sleep(3)


def splitDomain(fqdnStr):
    """Split an FQDN as a string into its subdomain and top-level domain

    :fqdnStr: FQDN to be split
    :returns: tuple of the form (subdomain, top-level domain)

    """
    splitStr = fqdnStr.split(".")
    domainTup = ".".join(splitStr[:-2]), ".".join(splitStr[-2:])
    if domainTup[0] == "":
        raise NoSubdomainError(
            f"{fqdnStr} does not contain a subdomain and top-level domain"
        )
    else:
        return domainTup
