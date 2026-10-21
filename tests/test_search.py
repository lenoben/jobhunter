import pytest

from core import db
from core.filters import load_filters, seed_default_filters
from core.models import JobPosting
from core.search import run_search
from core.sources import SOURCES


class FakeSource:
    key = "fake"

    def __init__(self, postings):
        self.postings = postings
        self.last_errors = []
        self.detail_calls = 0

    def search(self, f, limit):
        return [JobPosting(**vars(p)) for p in self.postings][:limit]  # fresh copies each call

    def fetch_details(self, job):
        self.detail_calls += 1
        job.description = job.description or "Fetched description."
        return job


def P(url, title, company="ACME GmbH", location="Mannheim", **kw):
    return JobPosting(source="fake", url=url, title=title, company=company, location=location, **kw)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.migrate(c)
    seed_default_filters(c)
    yield c
    c.close()


@pytest.fixture
def fake():
    src = FakeSource([
        P("https://jobs.example/1?utm_source=x", "Backend Developer (m/w/d)", salary_text="60.000 €"),
        P("https://jobs.example/2", "Python Developer", description="We require unrestricted work authorization."),
        P("https://jobs.example/3", "Go Developer", salary_text="3.000 € / Monat", description="Go."),
        P("https://jobs.example/4", "Freelance Python Developer"),
        P("https://other.example/99", "Backend-Developer (all genders)", company="Acme"),  # same job, other board
    ])
    SOURCES["fake"] = src
    yield src
    del SOURCES["fake"]


def test_second_identical_search_inserts_nothing(conn, fake):
    f = load_filters(conn)[0]
    first = run_search(conn, f, sources=["fake"])
    assert len(first.new) == 3 and len(first.skipped) == 1 and first.duplicates == 1
    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == 4

    second = run_search(conn, f, sources=["fake"])
    assert second.new == [] and second.skipped == [] and second.duplicates == 5
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == count


def test_screening_sets_status_and_history(conn, fake):
    f = load_filters(conn)[0]
    run_search(conn, f, sources=["fake"])
    rows = {r["title"]: r for r in conn.execute("SELECT * FROM jobs")}

    ok = rows["Backend Developer (m/w/d)"]
    assert ok["status"] == "new" and ok["salary_flag"] == "ok" and ok["salary_annual_eur"] == 60000

    wa = rows["Python Developer"]
    assert wa["status"] == "needs_attention" and wa["attention_reason"] == "work_authorization"
    assert wa["salary_flag"] == "salary_unknown"

    low = rows["Go Developer"]
    assert low["status"] == "needs_attention" and low["attention_reason"] == "below_blue_card_threshold"
    assert low["salary_annual_eur"] == 36000

    assert rows["Freelance Python Developer"]["status"] == "skipped"

    history = conn.execute("SELECT COUNT(*) FROM status_history").fetchone()[0]
    assert history == 4
    note = conn.execute("SELECT note FROM status_history WHERE job_id = ?", (wa["id"],)).fetchone()[0]
    assert "unrestricted work authorization" in note


def test_work_permit_checks_off_flags_nothing(conn, fake):
    """EU citizens turn the §5a work-permit checks off: the salary is still read, nothing is flagged."""
    conn.execute("UPDATE settings SET value = '0' WHERE key = 'work_permit_checks'")
    run_search(conn, load_filters(conn)[0], sources=["fake"])
    rows = {r["title"]: r for r in conn.execute("SELECT * FROM jobs")}
    assert rows["Python Developer"]["status"] == "new"
    low = rows["Go Developer"]
    assert (low["status"], low["salary_flag"], low["salary_annual_eur"]) == ("new", "ok", 36000)


def test_details_fetched_only_for_new_unskipped_jobs(conn, fake):
    f = load_filters(conn)[0]
    run_search(conn, f, sources=["fake"])
    assert fake.detail_calls == 1  # only job 1 lacked a description; job 4 was skipped first


def test_dry_run_stores_nothing(conn, fake):
    f = load_filters(conn)[0]
    r = run_search(conn, f, sources=["fake"], dry_run=True)
    assert len(r.new) == 3
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_failing_source_is_recorded_and_others_continue(conn, fake):
    class Broken(FakeSource):
        key = "broken"
        def search(self, f, limit):
            raise RuntimeError("boom")
    SOURCES["broken"] = Broken([])
    try:
        r = run_search(conn, load_filters(conn)[0], sources=["broken", "fake"])
    finally:
        del SOURCES["broken"]
    assert r.errors and r.errors[0]["source"] == "broken"
    assert len(r.new) == 3
