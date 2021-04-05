import pytest
import vmManagement
from requests.exceptions import HTTPError

DUMMY_ID = 523529
GOOD_STATUS_CODE = 200
BAD_STATUS_CODE = 500
DUMMY_TOKEN = "dummyToken"
DUMMY_SUB_DOMAIN = "subdomain"
DUMMY_DOMAIN = "domain.com"
DUMMY_IP = "0.0.0.0"
DUMMY_REGION = "region"
DEFAULT_REGION = "someregion"
DUMMY_HEADER = {"Authorization": f"Bearer {DUMMY_TOKEN}"}


class MockResponse:
    def __init__(self, status_code, kwargsDict, jsonType=None):
        # choose whether to throw HTTPError when raise_for_status() called
        self.status_code = status_code
        # choose which type of JSON to return (tailored to different API endpoints)
        self.jsonType = jsonType
        # all API calls should be made with bearer token header, so always check
        assert kwargsDict["headers"] == DUMMY_HEADER

    def raise_for_status(self):
        if self.status_code < 200 or self.status_code >= 400:
            raise HTTPError(f"Bad status code: {self.status_code}")

    def json(self):
        if self.jsonType == "chooseRegionNoDroplets":
            return {"droplets": []}
        elif self.jsonType == "chooseRegionOtherDroplets":
            return {
                "droplets": [
                    {"region": {"slug": DUMMY_REGION}},
                    {"region": {"slug": DUMMY_REGION}},
                    {"region": {"slug": "other"}},
                ]
            }
        elif self.jsonType == "addSSHKey":
            return {"ssh_key": {"id": DUMMY_ID}}
        elif self.jsonType == "waitForVM":
            return {
                "droplet": {
                    "networks": {
                        "v4": [
                            {
                                "type": "private",
                                "ip_address": "3.4.0.1",
                            },
                            {
                                "type": "public",
                                "ip_address": DUMMY_IP,
                            },
                        ]
                    }
                }
            }


class TestAddSSHKey:
    def test_good_addSSHKey(self, monkeypatch):
        """Add SSH key correctly"""

        monkeypatch.setattr(
            vmManagement.requests,
            "post",
            lambda *args, **kwargs: MockResponse(
                GOOD_STATUS_CODE, kwargs, jsonType="addSSHKey"
            ),
        )
        sshId = vmManagement.addSSHKey(DUMMY_TOKEN, "dummyKey", "dummyContent")
        assert sshId == DUMMY_ID

    def test_bad_addSSHKey(self, monkeypatch):
        """Add SSH key but get bad response status code"""

        monkeypatch.setattr(
            vmManagement.requests,
            "post",
            lambda *args, **kwargs: MockResponse(
                BAD_STATUS_CODE, kwargs, jsonType="addSSHKey"
            ),
        )
        with pytest.raises(HTTPError):
            vmManagement.addSSHKey(DUMMY_TOKEN, "dummyKey", "dummyContent")


class TestCreateARecord:
    def test_good_createARecord(self, mocker):
        mocker.patch(
            "vmManagement.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(GOOD_STATUS_CODE, kwargs),
        )
        vmManagement.createARecord(
            DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_IP
        )
        vmManagement.requests.post.assert_called_once()
        # API endpoint should have domain name in it
        assert DUMMY_DOMAIN in vmManagement.requests.post.call_args.args[0]

    def test_bad_createARecord(self, monkeypatch):
        """Create A record but get bad response status code"""

        monkeypatch.setattr(
            vmManagement.requests,
            "post",
            lambda *args, **kwargs: MockResponse(BAD_STATUS_CODE, kwargs),
        )
        with pytest.raises(HTTPError):
            vmManagement.createARecord(
                DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_IP
            )


class TestWaitForVM:
    def test_immediate_response(self, mocker):
        # no need to sleep in test cases
        mocker.patch("vmManagement.time.sleep")
        mocker.patch(
            "vmManagement.requests.get",
            side_effect=lambda *args, **kwargs: MockResponse(
                GOOD_STATUS_CODE, kwargs, jsonType="waitForVM"
            ),
        )

        vmIp = vmManagement.waitForVM(DUMMY_TOKEN, DUMMY_ID)
        vmManagement.time.sleep.assert_called_once_with(5)
        vmManagement.requests.get.assert_called_once()

        # droplet ID should be present in API endpoint
        assert str(DUMMY_ID) in vmManagement.requests.get.call_args.args[0]

        # returned in "waitForVM" case of MockResponse().json()
        assert vmIp == DUMMY_IP


class TestCreateVM:
    def test_bad_vm_request(self, monkeypatch):
        """Create VM but get bad response status code"""
        monkeypatch.setattr(
            vmManagement.requests,
            "post",
            lambda *args, **kwargs: MockResponse(BAD_STATUS_CODE, kwargs),
        )
        with pytest.raises(HTTPError):
            vmManagement.createVM(
                DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_REGION, DUMMY_ID
            )


class TestChooseRegion:
    def test_bad_region(self, monkeypatch):
        """Choose region but get bad response status code"""
        monkeypatch.setattr(
            vmManagement.requests,
            "get",
            lambda *args, **kwargs: MockResponse(
                BAD_STATUS_CODE, kwargs, jsonType="chooseRegionNoDroplets"
            ),
        )
        with pytest.raises(HTTPError):
            vmManagement.chooseRegion(DUMMY_TOKEN, DEFAULT_REGION)

    def test_region_other_droplets(self, monkeypatch):
        """Choose region with other droplets present"""
        monkeypatch.setattr(
            vmManagement.requests,
            "get",
            lambda *args, **kwargs: MockResponse(
                GOOD_STATUS_CODE, kwargs, jsonType="chooseRegionOtherDroplets"
            ),
        )
        region = vmManagement.chooseRegion(DUMMY_TOKEN, DEFAULT_REGION)
        # DUMMY_REGION is most frequent region in returned JSON
        assert region == DUMMY_REGION

    def test_region_no_droplets(self, monkeypatch):
        """Choose region with no other droplets present"""
        monkeypatch.setattr(
            vmManagement.requests,
            "get",
            lambda *args, **kwargs: MockResponse(
                GOOD_STATUS_CODE, kwargs, jsonType="chooseRegionNoDroplets"
            ),
        )
        region = vmManagement.chooseRegion(DUMMY_TOKEN, DEFAULT_REGION)
        # make sure that function falls back to DEFAULT_REGION if no other droplets
        assert region == DEFAULT_REGION
