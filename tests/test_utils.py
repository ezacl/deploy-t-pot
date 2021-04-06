import pytest
from errors import NoSubdomainError, NotFoundError
from utils import findPassword, splitDomain


class TestFindPasword:

    """Test utils.findPassword function"""

    def test_find_no_whitespace(self):
        assert findPassword("PASSWORD user = pass", "user") == "pass"

    def test_find_with_ending_whitespace(self):
        assert findPassword("PASSWORD otherUser = newPass ", "otherUser") == "newPass"

    def test_find_with_starting_whitespace(self):
        assert findPassword(" PASSWORD otherUser = newPass", "otherUser") == "newPass"

    def test_not_right_prompt(self):
        with pytest.raises(NotFoundError):
            findPassword("PASSWOR test = testing", "test")

    def test_search_for_password(self):
        with pytest.raises(NotFoundError):
            findPassword("PASSWORD test = testing", "testing")


class TestSplitDomain:

    """Test utils.splitDomain function"""

    def test_one_subdomain(self):
        assert splitDomain("subdomain.domain.net") == ("subdomain", "domain.net")

    def test_two_subdomains(self):
        domainTup = ("lowerDomain.subdomain", "domain.net")
        assert splitDomain("lowerDomain.subdomain.domain.net") == domainTup

    def test_no_subdomain(self):
        with pytest.raises(NoSubdomainError):
            splitDomain("domain.gov")

    def test_no_subdomain_with_dot(self):
        with pytest.raises(NoSubdomainError):
            splitDomain(".domain.gov")
