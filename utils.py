import re
import socket
import time

from errors import NotFoundError


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

    :host: host of port to check
    :port: port number to check availability of
    :returns: None

    """
    while True:
        # there must be a way to do this without creating a new socket every time
        monitorSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if monitorSock.connect_ex((host, port)) == 0:
            monitorSock.close()
            break

        monitorSock.close()
        time.sleep(3)

    # give some extra time after successful connection for service to start up
    time.sleep(10)
