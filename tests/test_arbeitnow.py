import pytest

from core.sources.arbeitnow import _in_germany


@pytest.mark.parametrize("url,location,expected", [
    ("https://www.arbeitnow.com/jobs/companies/a/b-munich-1", "Munich", True),
    ("https://www.arbeitnow.com/jobs/companies/a/b-1", "", True),
    ("https://www.arbeitnow.com/jobs/companies/a/b-1", "Bayern, Deutschland", True),
    ("https://www.arbeitnow.com/jobs/companies/a/b-1", "Zürich", False),
    ("https://www.arbeitnow.com/jobs/companies/a/b-1", "Lyon, Auvergne-Rhône-Alpes", False),
    ("https://www.arbeitnow.ch/jobs/companies/a/remote-b-bern-1", "Remote job", False),
    ("https://www.arbeitnow.co.uk/jobs/companies/a/b-1", "", False),
    ("https://www.arbeitnow.fr/jobs/companies/a/b-1", "Paris", False),
    ("https://www.arbeitnow.nl/jobs/companies/a/b-1", "Berlin", False),
])
def test_in_germany(url, location, expected):
    assert _in_germany({"url": url, "location": location}) is expected
