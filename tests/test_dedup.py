import pytest

from core.dedup import canonical_url, fingerprint, normalise


@pytest.mark.parametrize("a, b", [
    ("https://www.example.com/jobs/123/?utm_source=x&utm_medium=y", "https://example.com/jobs/123"),
    ("HTTP://Example.COM/jobs/123#apply", "https://example.com/jobs/123"),
    ("https://example.com/jobs?id=5&gclid=abc&ref=feed", "https://example.com/jobs?id=5"),
    ("https://example.com/jobs?b=2&a=1", "https://example.com/jobs?a=1&b=2"),
    ("https://example.com//jobs///123//", "https://example.com/jobs/123"),
])
def test_canonical_generic(a, b):
    assert canonical_url(a) == b


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/4012345678/?refId=abc&trackingId=xyz&trk=public_jobs",
    "https://de.linkedin.com/jobs/view/backend-developer-m-w-d-at-acme-4012345678",
    "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=python",
])
def test_canonical_linkedin_reduces_to_job_id(url):
    assert canonical_url(url) == "https://linkedin.com/jobs/view/4012345678"


def test_canonical_indeed_keeps_only_jk():
    assert canonical_url("https://de.indeed.com/viewjob?jk=abc123&from=serp&vjs=3&tk=1h") == \
        "https://de.indeed.com/viewjob?jk=abc123"
    assert canonical_url("https://de.indeed.com/rc/clk?jk=abc123&bb=x") == "https://de.indeed.com/viewjob?jk=abc123"


def test_canonical_arbeitsagentur():
    assert canonical_url("https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1002716922-S?utm_source=x") == \
        "https://arbeitsagentur.de/jobsuche/jobdetail/10001-1002716922-S"


@pytest.mark.parametrize("raw, expected", [
    ("Backend Developer (m/w/d)", "backend developer"),
    ("Backend Developer (w/m/d)", "backend developer"),
    ("Backend Developer (all genders)", "backend developer"),
    ("Backend-Developer (M/F/D)!", "backend developer"),
    ("ACME GmbH", "acme"),
    ("ACME GmbH & Co. KG", "acme"),
    ("Müller AG", "müller"),
    ("Siemens Healthineers SE", "siemens healthineers"),
    ("  Data   Engineer  ", "data engineer"),
])
def test_normalise(raw, expected):
    assert normalise(raw) == expected


def test_fingerprint_same_job_across_boards():
    a = fingerprint("ACME GmbH", "Backend Developer (m/w/d)", "Mannheim, Baden-Württemberg, Germany")
    b = fingerprint("Acme", "Backend-Developer (all genders)", "68159 Mannheim")
    assert a == b


def test_fingerprint_differs_by_city_and_title():
    base = fingerprint("ACME", "Backend Developer", "Mannheim")
    assert base != fingerprint("ACME", "Backend Developer", "Berlin")
    assert base != fingerprint("ACME", "Frontend Developer", "Mannheim")


def test_fingerprint_without_company_uses_url():
    a = fingerprint(None, "Backend Developer", "Mannheim", "https://a.com/1")
    b = fingerprint(None, "Backend Developer", "Mannheim", "https://b.com/2")
    assert a != b
