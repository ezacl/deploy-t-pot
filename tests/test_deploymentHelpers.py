import string

import deploymentHelpers
import pytest
from errors import BadAPIRequestError, NotCreatedError

from .mockResponse import MockResponse

dummyUrl = "dummyhost:5601"
dummyUser = "dummyUser"
dummyPass = "dummyPass"

createdRoleName = "t_pot_writer"
createdUserName = "t_pot_internal"


class TestCreateTPotRole:
    jsonType = "createRole"

    def test_good_role(self, monkeypatch):
        """Create T-Pot role correctly"""
        monkeypatch.setattr(
            deploymentHelpers.requests,
            "post",
            lambda *args, **kwargs: MockResponse(jsonType=__class__.jsonType),
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
            lambda *args, **kwargs: MockResponse(
                jsonType=__class__.jsonType, userRoleCreated=False
            ),
        )
        with pytest.raises(NotCreatedError):
            deploymentHelpers.createTPotRole(dummyUrl, dummyUser, dummyPass)

    def test_bad_request_role(self, monkeypatch):
        """Create T-Pot role with bad API request"""
        monkeypatch.setattr(
            deploymentHelpers.requests,
            "post",
            lambda *args, **kwargs: MockResponse(
                statusError=True,
                jsonType=__class__.jsonType,
                userRoleCreated=False,
            ),
        )
        with pytest.raises(BadAPIRequestError):
            deploymentHelpers.createTPotRole(dummyUrl, dummyUser, dummyPass)


class TestCreateTPotUser:
    jsonType = "createUser"

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
            lambda *args, **kwargs: MockResponse(jsonType=__class__.jsonType),
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
            lambda *args, **kwargs: MockResponse(jsonType=__class__.jsonType),
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
            lambda *args, **kwargs: MockResponse(
                jsonType=__class__.jsonType, userRoleCreated=False
            ),
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
            lambda *args, **kwargs: MockResponse(
                statusError=True, jsonType=__class__.jsonType
            ),
        )
        with pytest.raises(BadAPIRequestError):
            deploymentHelpers.createTPotUser(dummyUrl, dummyUser, creatorPwd=dummyPass)
