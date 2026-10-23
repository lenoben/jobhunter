"""Target countries (core/countries.py), source coverage (core/search.covers), the 6-hour feed
cache and the remote boards Himalayas / Jobicy, plus jobspy's per-country searches. No network."""

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from core import countries
from core.models import SearchFilter
from core.search import covers
from core.sources import SOURCES
from core.sources.base import FeedCache
from core.sources.himalayas import Himalayas
from core.sources.jobicy import Jobicy


def test_parse_and_aliases():
    assert countries.parse("United States, UK; deutschland, remote, usa") == (["usa", "uk", "germany", "remote"], [])
    assert countries.parse("Atlantis, south  africa") == (["south africa"], ["Atlantis"])


def test_effective_countries_filter_overrides_setting():
    settings = {"search_countries": '["usa", "remote"]'}
    assert countries.effective([], settings) == ["usa", "remote"]
    assert countries.effective(["uk"], settings) == ["uk"]
    assert countries.effective([], {}) == ["germany"]            # existing installs keep Germany
    assert countries.effective([], {"search_countries": "not json"}) == ["germany"]


@pytest.mark.parametrize("geo,targets,ok", [
    ("Anywhere", ["usa"], True),
    ("Canada,  USA", ["usa"], True),
    ("EMEA", ["nigeria"], True),
    ("Europe", ["germany"], True),
    ("LATAM", ["usa"], False),
    ("Philippines", ["uk", "canada"], False),
    ("Philippines", ["remote"], True),
])
def test_geo_matches(geo, targets, ok):
    assert countries.geo_matches(geo, targets) is ok


def _f(**kw):
    return SearchFilter(name="t", keywords=["Software Engineer"], **kw)


def test_covers():
    us = _f(countries=["usa"])
    assert not covers(SOURCES["ba_jobsuche"], us) and not covers(SOURCES["arbeitnow"], us)
    assert covers(SOURCES["jobspy"], us) and covers(SOURCES["himalayas"], us) and covers(SOURCES["email_alerts"], us)
    assert covers(SOURCES["ba_jobsuche"], _f(countries=["germany", "remote"]))
    onsite = _f(countries=["usa"], work_modes=["onsite"])
    assert not covers(SOURCES["himalayas"], onsite) and not covers(SOURCES["jobicy"], onsite)


def test_feed_cache_reuses_within_six_hours(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "jh.db"))
    calls = []
    cache = FeedCache("demo")
    load = lambda: calls.append(1) or {"n": len(calls)}  # noqa: E731
    assert cache.fetch("u", load) == {"n": 1}
    assert cache.fetch("u", load) == {"n": 1} and len(calls) == 1 and cache.hits == 1
    file = next((tmp_path / "cache" / "demo").glob("*.json"))
    old = time.time() - 6 * 3600 - 5
    os.utime(file, (old, old))
    assert cache.fetch("u", load) == {"n": 2}                   # older than 6 h: fetched again


def _ts(days_ago):
    return int((datetime.now(timezone.utc) - timedelta(days=days_ago)).timestamp())


def test_himalayas_targets_and_seven_days(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "jh.db"))
    h = Himalayas()
    seen = []

    class Http:
        def get_json(self, url, params):
            seen.append(dict(params))
            return {"jobs": [
                {"title": "Senior Software Engineer", "companyName": "A", "applicationLink": "https://h/a",
                 "guid": "https://h/a", "pubDate": _ts(1), "locationRestrictions": ["United States"],
                 "employmentType": "Full Time", "minSalary": 100000, "maxSalary": 120000, "currency": "USD",
                 "salaryPeriod": "annual", "description": "<p>Go</p>"},
                {"title": "Software Engineer", "companyName": "B", "applicationLink": "https://h/b",
                 "guid": "https://h/b", "pubDate": _ts(9)},          # older than 7 days
                {"title": "Sales Manager", "companyName": "C", "applicationLink": "https://h/c",
                 "guid": "https://h/c", "pubDate": _ts(1)},          # keyword doesn't match
            ]}
    h._http = Http()
    jobs = h.search(_f(countries=["usa", "remote"], max_age_days=30), limit=10)
    assert [j.url for j in jobs] == ["https://h/a"]
    assert jobs[0].work_mode == "remote" and jobs[0].location == "Remote (United States)"
    assert jobs[0].salary_text == "100000 - 120000 USD per year"
    assert {"worldwide": "true"}.items() <= seen[0].items() and seen[1]["country"] == "US"
    h.search(_f(countries=["usa", "remote"], max_age_days=30), limit=10)
    assert len(seen) == 2                                        # second run: from the cache


def test_jobicy_one_download_matched_per_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "jh.db"))
    j = Jobicy()
    calls = []
    now = datetime.now(timezone.utc)

    class Http:
        def get_json(self, url, params):
            calls.append(params)
            return {"hasMore": False, "jobs": [
                {"id": 1, "url": "https://j/1", "jobTitle": "Software Engineer", "jobGeo": "Canada,  USA",
                 "pubDate": now.isoformat(), "jobType": ["Full-Time"]},
                {"id": 2, "url": "https://j/2", "jobTitle": "Software Engineer", "jobGeo": "Philippines",
                 "pubDate": now.isoformat()},
                {"id": 3, "url": "https://j/3", "jobTitle": "Software Engineer", "jobGeo": "Anywhere",
                 "pubDate": (now - timedelta(days=10)).isoformat()},
            ]}
    j._http = Http()
    us = j.search(_f(countries=["usa"]), limit=10)
    assert [p.url for p in us] == ["https://j/1"] and us[0].employment_type == "full_time"
    assert [p.url for p in j.search(_f(countries=["remote"]), limit=10)] == ["https://j/1", "https://j/2"]
    assert len(calls) == 1


def test_jobspy_searches_each_country(monkeypatch):
    import pandas as pd
    import jobspy
    from core.sources import jobspy_source

    calls = []
    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **kw: calls.append(kw) or pd.DataFrame())
    monkeypatch.setattr(jobspy_source.time, "sleep", lambda s: None)
    src = jobspy_source.JobSpySource()
    with pytest.raises(Exception):  # nothing found anywhere → "all jobspy sites failed"
        src.search(_f(countries=["nigeria", "uk", "remote"]), limit=9)
    by_site = [(c["site_name"][0], c["country_indeed"], c["location"], c.get("is_remote")) for c in calls]
    assert ("indeed", "nigeria", "Nigeria", None) in by_site
    assert not any(s == "glassdoor" and c == "nigeria" for s, c, *_ in by_site)   # no Glassdoor site there
    assert ("glassdoor", "uk", "United Kingdom", None) in by_site
    assert ("linkedin", "usa", "Worldwide", True) in by_site                     # remote: LinkedIn only
    assert all(c["results_wanted"] <= 3 for c in calls)                          # limit shared by 3 targets
