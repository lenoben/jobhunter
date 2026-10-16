"""Where to apply, re-evaluation, score-only evaluation and the run notifications
(user requests 2026-10-18)."""

import pytest

from core import db, jobs, manual, notify, runs
from core.filters import seed_default_filters
from core.models import JobPosting

POSTING = """Backend Developer (m/w/d)
ACME GmbH, Mannheim
Wir suchen eine/n Backend Developer mit Python und PostgreSQL für unser Plattform-Team.
Deine Aufgaben: REST-APIs entwickeln, Datenbanken betreuen, CI/CD verbessern.
"""


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(notify, "_config", lambda: ("token", "chat"))
    monkeypatch.setattr(notify, "_call", lambda method, token, **p: out.append(p) or {})
    return out


@pytest.fixture
def conn(tmp_path, monkeypatch, sent):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "a.db"))
    monkeypatch.setenv("JOBHUNTER_OUTPUT", str(tmp_path / "out"))
    c = db.connect()
    db.migrate(c)
    seed_default_filters(c)
    yield c
    c.close()


def _job(conn, n, status="new", fit=None):
    p = JobPosting(source="x", url=f"https://x.example/{n}", title=f"Job {n}", company="ACME", location="Mannheim",
                   canonical_url=f"x.example/{n}", fingerprint=f"fp{n}", description=POSTING)
    p.status = status
    jid = jobs.insert_job(conn, p)
    if fit is not None:
        conn.execute("UPDATE jobs SET fit_score = ? WHERE id = ?", (fit, jid))
    conn.commit()
    return jid


EVAL = dict(fit_notes="- ok", work_mode="hybrid", employment_type="full_time", language="de",
            apply_method="portal", decision="shortlist")


# ── where to apply ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    (POSTING + "Jetzt bewerben: https://acme.jobs.personio.de/job/123?apply", {"apply_url": "https://acme.jobs.personio.de/job/123?apply"}),
    (POSTING + "Mehr über uns: https://acme.example/about\nBewerbung über https://karriere.acme.example/form/7.",
     {"apply_url": "https://karriere.acme.example/form/7"}),
    (POSTING + "Bitte senden Sie Ihre Bewerbungsunterlagen an jobs@acme.example.", {"apply_email": "jobs@acme.example"}),
    (POSTING + "Apply via https://boards.greenhouse.io/acme/jobs/42", {"apply_url": "https://boards.greenhouse.io/acme/jobs/42"}),
    (POSTING + "Website: https://acme.example · Datenschutz: datenschutz@acme.example", {}),
])
def test_apply_target_from_text(text, expected):
    assert manual.apply_target_from_text(text, "https://x.example/posting") == expected


def test_apply_link_from_page_buttons():
    page = '<a href="/about">Über uns</a><a class="btn" href="/apply/42">Jetzt bewerben</a>'
    assert manual._apply_link_from_html(page, "https://jobs.acme.example/job/42") == "https://jobs.acme.example/apply/42"
    assert manual._apply_link_from_html('<a href="mailto:x@y.de">Bewerben</a>', "https://a.example/") is None


def test_add_job_takes_the_apply_link_from_the_text_or_the_user(conn):
    r = manual.add_manual_job(conn, "https://example.org/jobs/1",
                              POSTING + "Bewerben Sie sich hier: https://acme.softgarden.io/job/1/apply")
    assert jobs.get_job(conn, r["job_id"])["apply_url"] == "https://acme.softgarden.io/job/1/apply"
    r = manual.add_manual_job(conn, "https://example.org/jobs/2", POSTING.replace("Backend", "Frontend"),
                              apply_to="mailto:hr@acme.example")
    job = jobs.get_job(conn, r["job_id"])
    assert (job["apply_email"], job["apply_method"], job["apply_url"]) == ("hr@acme.example", "email", None)
    with pytest.raises(manual.ManualJobError, match="where to apply"):
        manual.add_manual_job(conn, "https://example.org/jobs/3", POSTING, apply_to="call Mrs X")


def test_evaluation_keeps_the_apply_email(conn):
    jid = _job(conn, 1)
    manual.set_apply_target(conn, jid, "hr@acme.example")
    jobs.evaluate_job(conn, jid, 70, **EVAL)
    job = jobs.get_job(conn, jid)
    assert (job["apply_email"], job["apply_method"]) == ("hr@acme.example", "email")


# ── scoring and re-evaluation ───────────────────────────────────────────────

def test_unscored_job_in_another_status_is_scored_without_status_change(conn):
    jid = _job(conn, 1, "docs_ready")
    before = runs.tailored_since(conn, "2000-01-01")
    assert jobs.evaluate_job(conn, jid, 55, **(EVAL | {"decision": "skip"})) == "docs_ready"
    assert jobs.get_job(conn, jid)["fit_score"] == 55
    assert runs.tailored_since(conn, "2000-01-01") == before  # a score is not "docs ready"
    with pytest.raises(ValueError, match="already scored"):
        jobs.evaluate_job(conn, jid, 60, **EVAL)


def test_reevaluate(conn):
    skipped = _job(conn, 1, "skipped", fit=40)
    ready = _job(conn, 2, "docs_ready", fit=70)
    assert manual.reevaluate(conn, skipped)["status"] == "new"
    r = manual.reevaluate(conn, ready)
    job = jobs.get_job(conn, ready)
    assert r["status"] == "docs_ready" and job["status"] == "docs_ready" and job["fit_score"] is None


def test_evaluate_trigger_skips_the_time_guard(conn):
    runs.finish_run(conn, runs.start_run(conn, "scheduled"))
    with pytest.raises(runs.RunRefused):
        runs.start_run(conn, "manual")
    runs.finish_run(conn, runs.start_run(conn, "evaluate"))


# ── automatic clean-up ──────────────────────────────────────────────────────

def test_purge_old_jobs_keeps_what_matters_and_dedups(conn):
    old = {n: _job(conn, n, status) for n, status in
           [(1, "skipped"), (2, "new"), (3, "applied"), (4, "skipped"), (5, "shortlisted")]}
    conn.execute("UPDATE jobs SET favorite = 1 WHERE id = ?", (old[4],))
    conn.execute("UPDATE jobs SET docs_requested = 'cv' WHERE id = ?", (old[5],))
    conn.execute("UPDATE jobs SET updated_at = datetime('now', '-40 days')")
    fresh = _job(conn, 6, "skipped")
    assert jobs.purge_old_jobs(conn) == 0                     # 0 days = off
    conn.execute("UPDATE settings SET value = '30' WHERE key = 'job_retention_days'")
    assert jobs.purge_old_jobs(conn, dry_run=True) == 2
    assert jobs.purge_old_jobs(conn) == 2
    left = {r[0] for r in conn.execute("SELECT id FROM jobs")}
    assert left == {old[3], old[4], old[5], fresh}            # applied, favourite, requested, recent
    # R8: a deleted job is still "seen", so a search never inserts it again …
    assert jobs.find_seen(conn, "x.example/1") == {"id": None, "status": "deleted"}
    assert jobs.find_seen(conn, "x.example/1", include_deleted=False) is None
    # … but the user can add it again by hand (the tombstone is removed)
    conn.execute("UPDATE deleted_jobs SET canonical_url = 'https://x.example/1' WHERE canonical_url = 'x.example/1'")
    r = manual.add_manual_job(conn, "https://x.example/1", POSTING)
    assert r["created"] and jobs.is_seen(conn, "https://x.example/1")["job_id"] == r["job_id"]


# ── notifications ───────────────────────────────────────────────────────────

def test_docs_run_lists_written_and_waiting_jobs(conn):
    done, waiting = _job(conn, 1, "shortlisted", fit=72), _job(conn, 2, "shortlisted")
    conn.execute("UPDATE jobs SET docs_requested = 'cv' WHERE id IN (?, ?)", (done, waiting))
    run_id = runs.start_run(conn, "docs")
    jobs.set_status(conn, done, "docs_ready", "claude")
    conn.execute("UPDATE jobs SET docs_requested = NULL WHERE id = ?", (done,))
    run = runs.finish_run(conn, run_id)
    msg = notify.run_message(conn, run, runs.summary_line(run))
    assert msg.startswith("✍️ Requested documents: 1 written")
    assert "<b>Job 1</b> – ACME, Mannheim (fit 72)" in msg and "⏳ Still waiting" in msg and "<b>Job 2</b>" in msg


def test_single_run_reports_the_score(conn):
    jid = _job(conn, 1)
    run_id = runs.start_run(conn, "single")
    jobs.evaluate_job(conn, jid, 66, **EVAL)
    run = runs.finish_run(conn, run_id)
    assert "🧮 <b>Job 1</b> – ACME, Mannheim: fit 66 → shortlisted ✅" in notify.run_message(conn, run, "")


def test_notification_toggles(conn, sent):
    run_id = runs.start_run(conn, "docs")
    run = runs.finish_run(conn, run_id)
    conn.execute("UPDATE settings SET value = '0' WHERE key = 'notify_docs_ready'")
    assert notify.notify_run_finished(conn, run, "") == "nothing to send" and sent == []
    conn.execute("UPDATE settings SET value = '0' WHERE key = 'notify_failures'")
    assert notify.notify_run_failed(conn, "boom") == "disabled"
    conn.execute("UPDATE settings SET value = '1' WHERE key = 'notify_failures'")
    assert notify.notify_run_refused(conn, "docs", "run 3 is still running") == "sent"
    assert sent[-1]["text"] == "⏸ Generate now couldn't start: run 3 is still running"
