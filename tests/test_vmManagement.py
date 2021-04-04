import pytest
import requests
import vmManagement
from requests.exceptions import HTTPError

DUMMY_SSH_ID = 523529
GOOD_STATUS_CODE = 200
BAD_STATUS_CODE = 500
DUMMY_TOKEN = "dummyToken"
DUMMY_SUB_DOMAIN = "subdomain"
DUMMY_DOMAIN = "domain.com"
DUMMY_IP = "0.0.0.0"
DUMMY_REGION = "region"
DEFAULT_REGION = "someregion"


class MockResponse:
    def __init__(self, status_code, headers, chooseRegion=False, otherDroplets=True):
        self.status_code = status_code
        self.chooseRegion = chooseRegion
        self.otherDroplets = otherDroplets
        # all API calls should be made with bearer token header, so always check
        assert headers == {"Authorization": f"Bearer {DUMMY_TOKEN}"}

    def raise_for_status(self):
        if self.status_code < 200 or self.status_code >= 400:
            raise HTTPError(f"Bad status code: {self.status_code}")

    def json(self):
        if self.chooseRegion:
            if self.otherDroplets:
                return {
                    "droplets": [
                        {"region": {"slug": DUMMY_REGION}},
                        {"region": {"slug": DUMMY_REGION}},
                        {"region": {"slug": "other"}},
                    ]
                }
            else:
                return {"droplets": []}
        else:
            return {"ssh_key": {"id": DUMMY_SSH_ID}}


class TestAddSSHKey:
    def test_good_addSSHKey(self, monkeypatch):
        """Add SSH key correctly"""

        monkeypatch.setattr(
            requests,
            "post",
            lambda *args, **kwargs: MockResponse(GOOD_STATUS_CODE, kwargs["headers"]),
        )
        sshId = vmManagement.addSSHKey(DUMMY_TOKEN, "dummyKey", "dummyContent")
        assert sshId == DUMMY_SSH_ID

    def test_bad_addSSHKey(self, monkeypatch):
        """Add SSH key but get bad response status code"""

        monkeypatch.setattr(
            requests,
            "post",
            lambda *args, **kwargs: MockResponse(BAD_STATUS_CODE, kwargs["headers"]),
        )
        with pytest.raises(HTTPError):
            vmManagement.addSSHKey(DUMMY_TOKEN, "dummyKey", "dummyContent")


class TestCreateARecord:
    def test_bad_createARecord(self, monkeypatch):
        """Create A record but get bad response status code"""

        monkeypatch.setattr(
            requests,
            "post",
            lambda *args, **kwargs: MockResponse(BAD_STATUS_CODE, kwargs["headers"]),
        )
        with pytest.raises(HTTPError):
            vmManagement.createARecord(
                DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_IP
            )


class TestCreateVM:
    def test_bad_vm_request(self, monkeypatch):
        """Create VM but get bad response status code"""
        monkeypatch.setattr(
            requests,
            "post",
            lambda *args, **kwargs: MockResponse(BAD_STATUS_CODE, kwargs["headers"]),
        )
        with pytest.raises(HTTPError):
            vmManagement.createVM(
                DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_REGION, DUMMY_SSH_ID
            )


class TestChooseRegion:
    def test_bad_region(self, monkeypatch):
        """Choose region but get bad response status code"""
        monkeypatch.setattr(
            requests,
            "get",
            lambda *args, **kwargs: MockResponse(
                BAD_STATUS_CODE, kwargs["headers"], chooseRegion=True
            ),
        )
        with pytest.raises(HTTPError):
            vmManagement.chooseRegion(DUMMY_TOKEN, DEFAULT_REGION)

    def test_region_other_droplets(self, monkeypatch):
        """Choose region with other droplets present"""
        monkeypatch.setattr(
            requests,
            "get",
            lambda *args, **kwargs: MockResponse(
                GOOD_STATUS_CODE, kwargs["headers"], chooseRegion=True
            ),
        )
        region = vmManagement.chooseRegion(DUMMY_TOKEN, DEFAULT_REGION)
        # DUMMY_REGION is most frequent region in returned JSON
        assert region == DUMMY_REGION

    def test_region_no_droplets(self, monkeypatch):
        """Choose region with no other droplets present"""
        monkeypatch.setattr(
            requests,
            "get",
            lambda *args, **kwargs: MockResponse(
                GOOD_STATUS_CODE,
                kwargs["headers"],
                chooseRegion=True,
                otherDroplets=False,
            ),
        )
        region = vmManagement.chooseRegion(DUMMY_TOKEN, DEFAULT_REGION)
        # make sure that function falls back to DEFAULT_REGION if no other droplets
        assert region == DEFAULT_REGION
