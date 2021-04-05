import pytest
import vmManagement
from requests.exceptions import HTTPError

from .mockResponse import (DUMMY_ID, DUMMY_IP, DUMMY_REGION, DUMMY_TOKEN,
                           MockResponse)

DUMMY_SUB_DOMAIN = "subdomain"
DUMMY_DOMAIN = "domain.com"
DEFAULT_REGION = "someregion"
DUMMY_SSH_KEY = "ssh key text"
DUMMY_LOGGING_OBJ = {"host": f"{DUMMY_SUB_DOMAIN}.{DUMMY_DOMAIN}"}
DUMMY_SENSOR_OBJS = [
    {"host": f"{DUMMY_SUB_DOMAIN}.{DUMMY_DOMAIN}"},
    {"host": f"{DUMMY_SUB_DOMAIN}.{DUMMY_DOMAIN}"},
    {"host": f"{DUMMY_SUB_DOMAIN}.{DUMMY_DOMAIN}"},
]


class TestAddSSHKey:

    jsonType = "addSSHKey"

    def test_good_addSSHKey(self, monkeypatch):
        """Add SSH key correctly"""

        monkeypatch.setattr(
            vmManagement.requests,
            "post",
            lambda *args, **kwargs: MockResponse(
                kwargsDict=kwargs, jsonType=__class__.jsonType
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
                statusError=True, kwargsDict=kwargs, jsonType=__class__.jsonType
            ),
        )
        with pytest.raises(HTTPError):
            vmManagement.addSSHKey(DUMMY_TOKEN, "dummyKey", "dummyContent")


class TestCreateARecord:
    def test_good_createARecord(self, mocker):
        """Create A record correctly"""
        mocker.patch(
            "vmManagement.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(kwargsDict=kwargs),
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
            lambda *args, **kwargs: MockResponse(statusError=True, kwargsDict=kwargs),
        )
        with pytest.raises(HTTPError):
            vmManagement.createARecord(
                DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_IP
            )


class TestWaitForVM:

    jsonType = "waitForVM"

    def test_immediate_response(self, mocker):
        """Have API respond with IP address immediately"""
        # no need to sleep in test cases
        mocker.patch("vmManagement.time.sleep")
        mocker.patch(
            "vmManagement.requests.get",
            side_effect=lambda *args, **kwargs: MockResponse(
                kwargsDict=kwargs, jsonType=__class__.jsonType
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

    jsonType = "createVM"

    def test_bad_vm_request(self, monkeypatch):
        """Create VM but get bad response status code"""
        monkeypatch.setattr(
            vmManagement.requests,
            "post",
            lambda *args, **kwargs: MockResponse(statusError=True, kwargsDict=kwargs),
        )
        with pytest.raises(HTTPError):
            vmManagement.createVM(
                DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_REGION, DUMMY_ID
            )

    def test_good_vm_request(self, mocker):
        """Create VM correctly"""
        mocker.patch(
            "vmManagement.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                kwargsDict=kwargs, jsonType=__class__.jsonType
            ),
        )
        mocker.patch("vmManagement.waitForVM", return_value=DUMMY_IP)
        mocker.patch("vmManagement.createARecord")

        vmManagement.createVM(
            DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_REGION, DUMMY_ID
        )

        # check that both other (mocked) functions were called correctly
        vmManagement.waitForVM.assert_called_once_with(DUMMY_TOKEN, DUMMY_ID)
        vmManagement.createARecord.assert_called_once_with(
            DUMMY_TOKEN, DUMMY_SUB_DOMAIN, DUMMY_DOMAIN, DUMMY_IP
        )


class TestChooseRegion:

    jsonNoDroplets = "chooseRegionNoDroplets"
    jsonOtherDroplets = "chooseRegionOtherDroplets"

    def test_bad_region(self, monkeypatch):
        """Choose region but get bad response status code"""
        monkeypatch.setattr(
            vmManagement.requests,
            "get",
            lambda *args, **kwargs: MockResponse(
                statusError=True, kwargsDict=kwargs, jsonType=__class__.jsonNoDroplets
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
                kwargsDict=kwargs, jsonType=__class__.jsonOtherDroplets
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
                kwargsDict=kwargs, jsonType=__class__.jsonNoDroplets
            ),
        )
        region = vmManagement.chooseRegion(DUMMY_TOKEN, DEFAULT_REGION)
        # make sure that function falls back to DEFAULT_REGION if no other droplets
        assert region == DEFAULT_REGION


class TestCreateAllVMs:
    def test_correct_amount_createVM_calls(self, mocker):
        """Check that createAllVMs is called the appropriate number of times"""
        mocker.patch("vmManagement.addSSHKey", return_value=DUMMY_ID)
        mocker.patch("vmManagement.chooseRegion", return_value=DEFAULT_REGION)
        mocker.patch("vmManagement.createVM")

        vmManagement.createAllVMs(
            DUMMY_TOKEN, DUMMY_LOGGING_OBJ, DUMMY_SENSOR_OBJS, DUMMY_SSH_KEY
        )

        # createVM should be called an amount of times equal to the length of
        # DUMMY_SENSOR_OBJS + 1 for DUMMY_LOGGING_OBJ
        assert vmManagement.createVM.call_count == len(DUMMY_SENSOR_OBJS) + 1


class TestDeleteSSHKey:

    jsonType = "deleteSSHKey"

    def test_bad_delete(self, mocker):
        """Try to delete SSH key but return bad HTTP status code"""
        mocker.patch(
            "vmManagement.requests.get",
            side_effect=lambda *args, **kwargs: MockResponse(
                statusError=True, kwargsDict=kwargs, jsonType=__class__.jsonType
            ),
        )
        with pytest.raises(HTTPError):
            vmManagement.deleteSSHKey(DUMMY_TOKEN)

    def test_correct_delete(self, mocker):
        """Check that deleteSSHKey deletes the right key"""
        mocker.patch(
            "vmManagement.requests.get",
            side_effect=lambda *args, **kwargs: MockResponse(
                kwargsDict=kwargs, jsonType=__class__.jsonType
            ),
        )
        mocker.patch(
            "vmManagement.requests.delete",
            side_effect=lambda *args, **kwargs: MockResponse(kwargsDict=kwargs),
        )
        vmManagement.deleteSSHKey(DUMMY_TOKEN)

        vmManagement.requests.delete.assert_called_once()
        # DUMMY_ID returned in JSON of requests.get should be in the API endpoint for
        # the requests.delete call
        assert str(DUMMY_ID) in vmManagement.requests.delete.call_args.args[0]
