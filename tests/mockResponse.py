from requests.exceptions import HTTPError

DUMMY_ID = 523529
DUMMY_TOKEN = "dummyToken"
DUMMY_IP = "0.0.0.0"
DUMMY_REGION = "region"
DUMMY_HEADER = {"Authorization": f"Bearer {DUMMY_TOKEN}"}


class MockResponse:

    """Class mocking requests.Response class for use in testing"""

    def __init__(
        self, statusError=False, kwargsDict=None, jsonType=None, userRoleCreated=True
    ):
        # choose whether to throw HTTPError when raise_for_status() called
        self.status_error = statusError
        # choose which type of JSON to return (tailored to different API endpoints)
        self.jsonType = jsonType
        # whether T-Pot user/role was created (for test_deploymentHelpers.py)
        self.userRoleCreated = userRoleCreated

        self.text = "some dummy error text"

        # all DigitalOcean API calls should be made with bearer token header, so check
        if kwargsDict is not None:
            assert kwargsDict["headers"] == DUMMY_HEADER

    def raise_for_status(self):
        if self.status_error:
            raise HTTPError(f"Bad status code: {self.status_error}")

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
        elif self.jsonType == "createVM":
            return {"droplet": {"id": DUMMY_ID}}
        elif self.jsonType == "createRole":
            return {"role": {"created": self.userRoleCreated}}
        elif self.jsonType == "createUser":
            return {"created": self.userRoleCreated}
        else:
            return {}
