import pytest
from errors import NotFoundError
from utils import findPassword


def test_findPassword():
    """Test utils.findPassword function"""

    assert findPassword("PASSWORD user = pass", "user") == "pass"
    assert findPassword("PASSWORD otherUser = newPass ", "otherUser") == "newPass"
    assert findPassword(" PASSWORD otherUser = newPass", "otherUser") == "newPass"

    with pytest.raises(NotFoundError):
        findPassword("PASSWOR test = testing", "test")
        findPassword("PASSWORD test = testing", "testing")
