"""Manually added jobs and full postings (user requests 2026-10-16)."""

import pytest

from core import db, jobs, manual
from core.filters import seed_default_filters

POSTING = """Backend Developer (m/w/d)
ACME GmbH, Mannheim
Wir suchen eine/n Backend Developer mit Python und PostgreSQL für unser Plattform-Team.
Deine Aufgaben: REST-APIs entwickeln, Datenbanken betreuen, CI/CD verbessern.
Gehalt: 60.000 € – 70.000 € brutto pro Jahr
"""


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "m.db"))
    c = db.connect()
    db.migrate(c)
    seed_default_filters(c)
    yield c
    c.close()


def test_add_with_pasted_text_is_screened_and_filed(conn, monkeypatch):
    monkeypatch.setattr(manual, "fetch_posting", lambda url: pytest.fail("no fetch when text is pasted"))
    r = manual.add_manual_job(conn, "https://www.linkedin.com/jobs/view/4000000009/?trk=x", POSTING)
    job = jobs.get_job(conn, r["job_id"])
    assert r["created"] and job["status"] == "new" and job["source"] == "manual"
    assert job["title"] == "Backend Developer (m/w/d)" and job["salary_annual_eur"] == 70000
    assert job["filter_id"] is not None                     # matched "Backend Developer" → Software / Backend
    assert job["canonical_url"] == "https://linkedin.com/jobs/view/4000000009"


def test_add_known_job_adds_the_text_instead(conn):
    a = manual.add_manual_job(conn, "https://example.org/jobs/1", POSTING, title="Backend Developer")
    b = manual.add_manual_job(conn, "https://example.org/jobs/1?utm_source=x", POSTING + "\nMehr Details …")
    assert b["job_id"] == a["job_id"] and not b["created"] and "already known" in b["note"]


def test_login_pages_are_never_fetched(conn):
    with pytest.raises(manual.ManualJobError, match="needs a login"):
        manual.add_manual_job(conn, "https://app.instaffo.com/candidate/job/48b4a466-59e2-4eb4-a131-092fbfb0f59f")
    with pytest.raises(manual.ManualJobError, match="needs a login"):
        manual.fetch_posting("https://de.linkedin.com/jobs/view/123")


def test_fetch_uses_jsonld(conn, monkeypatch):
    page = """<html><head><title>x</title><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting","title":"Python Developer (m/w/d)",
     "hiringOrganization":{"@type":"Organization","name":"Example AG"},
     "jobLocation":{"@type":"Place","address":{"addressLocality":"Heidelberg"}},
     "description":"<p>Python, FastAPI, PostgreSQL.</p><ul><li>Remote möglich</li></ul>","datePosted":"2026-10-10"}
    </script></head><body>…</body></html>"""

    class Resp:
        status_code, text, url = 200, page, "https://jobs.smartrecruiters.com/ExampleAG/744000-python-developer"

    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return Resp()

    monkeypatch.setattr(manual.httpx, "Client", Client)
    r = manual.add_manual_job(conn, "https://jobs.smartrecruiters.com/ExampleAG/744000-python-developer")
    job = jobs.get_job(conn, r["job_id"])
    assert (job["title"], job["company"], job["location"]) == ("Python Developer (m/w/d)", "Example AG", "Heidelberg")
    assert "FastAPI" in job["description"] and "• Remote möglich" in job["description"]


def test_update_posting_resets_for_evaluation(conn):
    from core.models import JobPosting
    p = JobPosting(source="email_alerts", url="https://linkedin.com/jobs/view/1", title="Go Developer",
                   company="X", canonical_url="https://linkedin.com/jobs/view/1", fingerprint="fp1")
    p.status = "skipped"
    jid = jobs.insert_job(conn, p)
    conn.execute("UPDATE jobs SET fit_score = 40, fit_notes = 'title only' WHERE id = ?", (jid,))
    conn.commit()
    r = manual.update_posting(conn, jid, POSTING)
    job = jobs.get_job(conn, jid)
    assert r["status"] == "new" and job["fit_score"] is None and "PostgreSQL" in job["description"]
    assert jobs.history(conn, jid)[-1]["changed_by"] == "user"
    # a full text that demands unrestricted work authorization goes to needs_attention instead
    r = manual.update_posting(conn, jid, POSTING + "\nVoraussetzung: uneingeschränkte Arbeitserlaubnis.")
    assert r["status"] == "needs_attention"
    with pytest.raises(manual.ManualJobError, match="full posting"):
        manual.update_posting(conn, jid, "too short")
