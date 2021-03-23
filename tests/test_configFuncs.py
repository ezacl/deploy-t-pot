import pytest
import requests
from configFuncs import createTPotRole
from errors import NotCreatedError


class GoodRoleResponse:

    """Mock requests object when everything went well"""

    @staticmethod
    def raise_for_status():
        pass

    @staticmethod
    def json():
        return {"role": {"created": True}}


class NotCreatedRoleResponse:

    """Mock requests object when role was not created"""

    def __init__(self):
        self.text = "some error"

    @staticmethod
    def raise_for_status():
        pass

    @staticmethod
    def json():
        return {"role": {"created": False}}


@pytest.fixture
def mock_goodRoleResponse(monkeypatch):
    def mock_post(*args, **kwargs):
        return GoodRoleResponse()

    monkeypatch.setattr(requests, "post", mock_post)


@pytest.fixture
def mock_notCreatedRoleResponse(monkeypatch):
    def mock_post(*args, **kwargs):
        return NotCreatedRoleResponse()

    monkeypatch.setattr(requests, "post", mock_post)


def test_goodCreateTPotRole(mock_goodRoleResponse):
    assert createTPotRole("dummyhost:5601", "dummyUser", "dummyPass") == "t_pot_writer"


def test_notCreateCreateTPotRole(mock_notCreatedRoleResponse):
    with pytest.raises(NotCreatedError):
        createTPotRole("dummyhost:5601", "dummyUser", "dummyPass")
