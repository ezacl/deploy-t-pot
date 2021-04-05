# from deploymentHelpers import createTPotRole, createTPotUser
import string

import deploymentHelpers
import pytest
from errors import BadAPIRequestError, NotCreatedError
from requests.exceptions import HTTPError

dummyUrl = "dummyhost:5601"
dummyUser = "dummyUser"
dummyPass = "dummyPass"

createdRoleName = "t_pot_writer"
createdUserName = "t_pot_internal"


class RoleResponse:

    """Mock requests object for createTPotRole and createTPotUser"""

    def __init__(self, role=True, badRequest=False, created=True):
        self.role = role
        self.badRequest = badRequest
        self.created = created
        self.text = "dummy error text"

    def raise_for_status(self):
        if self.badRequest:
            raise HTTPError

    def json(self):
        """Return appropriate JSON format depending on if called by createTPotRole or
        createTPotUser"""
        if self.role:
            return {"role": {"created": self.created}}
        else:
            return {"created": self.created}


class TestCreateTPotRole:
    def test_good_role(self, monkeypatch):
        """Create T-Pot role correctly"""
        monkeypatch.setattr(
            deploymentHelpers.requests, "post", lambda *args, **kwargs: RoleResponse()
        )
        assert (
            deploymentHelpers.createTPotRole(dummyUrl, dummyUser, dummyPass)
            == createdRoleName
        )

    def test_not_created_role(self, monkeypatch):
        """Try to create T-Pot role but don't get role created"""
        monkeypatch.setattr(
            deploymentHelpers.requests,
            "post",
            lambda *args, **kwargs: RoleResponse(created=False),
        )
        with pytest.raises(NotCreatedError):
            deploymentHelpers.createTPotRole(dummyUrl, dummyUser, dummyPass)

    def test_bad_request_role(self, monkeypatch):
        """Create T-Pot role with bad API request"""
        monkeypatch.setattr(
            deploymentHelpers.requests,
            "post",
            lambda *args, **kwargs: RoleResponse(badRequest=True),
        )
        with pytest.raises(BadAPIRequestError):
            deploymentHelpers.createTPotRole(dummyUrl, dummyUser, dummyPass)


class TestCreateTPotUser:
    def test_good_user_no_pass(self, monkeypatch):
        """Create T-Pot user correctly with no password"""
        # mock createTPotRole because it has been tested above
        monkeypatch.setattr(
            deploymentHelpers, "createTPotRole", lambda *args, **kwargs: createdRoleName
        )
        # mock requests.post() for API requests
        monkeypatch.setattr(
            deploymentHelpers.requests,
            "post",
            lambda *args, **kwargs: RoleResponse(role=False),
        )

        userTup = deploymentHelpers.createTPotUser(
            dummyUrl, dummyUser, creatorPwd=dummyPass
        )
        assert userTup[0] == createdUserName
        assert len(userTup) == 2
        assert len(userTup[1]) == 20
        # check that randomly-generated password is only letters and numbers
        assert all(char in string.ascii_letters + string.digits for char in userTup[1])

    def test_good_user_pass(self, monkeypatch):
        """Create T-Pot user correctly with a password"""
        monkeypatch.setattr(
            deploymentHelpers, "createTPotRole", lambda *args, **kwargs: createdRoleName
        )
        monkeypatch.setattr(
            deploymentHelpers.requests,
            "post",
            lambda *args, **kwargs: RoleResponse(role=False),
        )
        userTup = deploymentHelpers.createTPotUser(
            dummyUrl, dummyUser, creatorPwd=dummyPass, createdPwd=dummyPass
        )
        assert userTup[0] == createdUserName
        assert len(userTup) == 2
        assert userTup[1] == dummyPass

    def test_not_created_user(self, monkeypatch):
        """Try to create T-Pot user but don't get user created"""
        monkeypatch.setattr(
            deploymentHelpers, "createTPotRole", lambda *args, **kwargs: createdRoleName
        )
        monkeypatch.setattr(
            deploymentHelpers.requests,
            "post",
            lambda *args, **kwargs: RoleResponse(role=False, created=False),
        )
        with pytest.raises(NotCreatedError):
            deploymentHelpers.createTPotUser(dummyUrl, dummyUser, creatorPwd=dummyPass)

    def test_bad_request_user(self, monkeypatch):
        """Create T-Pot user with bad API request"""
        monkeypatch.setattr(
            deploymentHelpers, "createTPotRole", lambda *args, **kwargs: createdRoleName
        )
        monkeypatch.setattr(
            deploymentHelpers.requests,
            "post",
            lambda *args, **kwargs: RoleResponse(role=False, badRequest=True),
        )
        with pytest.raises(BadAPIRequestError):
            deploymentHelpers.createTPotUser(dummyUrl, dummyUser, creatorPwd=dummyPass)
