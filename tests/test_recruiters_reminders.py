"""Recruiting agencies (no automatic documents) and job reminders (user requests 2026-10-28, core §16c)."""

from datetime import datetime

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from core import db, jobs, notify, recruiters, reminders, runs
from core.filters import seed_default_filters
from core.models import JobPosting


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(notify, "_config", lambda: ("token", "chat"))
    monkeypatch.setattr(notify, "_call", lambda method, token, **p: out.append(p) or {})
    return out


@pytest.fixture
def conn(tmp_path, monkeypatch, sent):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "r.db"))
    monkeypatch.setenv("JOBHUNTER_OUTPUT", str(tmp_path / "out"))
    c = db.connect()
    db.migrate(c)
    seed_default_filters(c)
    yield c
    c.close()


def _job(conn, n, company="ACME", status="new", fit=None):
    p = JobPosting(source="x", url=f"https://x.example/{n}", title=f"Job {n}", company=company, location="Berlin",
                   canonical_url=f"x.example/{n}", fingerprint=f"fp{n}", description="Python backend job")
    p.status = status
    jid = jobs.insert_job(conn, p)
    if fit is not None:
        conn.execute("UPDATE jobs SET fit_score = ? WHERE id = ?", (fit, jid))
    conn.commit()
    return jid


def _via(conn, jid):
    return conn.execute("SELECT via_recruiter FROM jobs WHERE id = ?", (jid,)).fetchone()[0]


EVAL = dict(fit_notes="- ok", work_mode="remote", employment_type="full_time", language="en",
            apply_method="portal", decision="shortlist")


def test_matching_is_by_whole_words_after_normalising():
    assert recruiters.matches("Hays AG", ["Hays"]) and recruiters.matches("HAYS Professional Solutions GmbH", ["hays"])
    assert not recruiters.matches("Haystack Inc", ["Hays"]) and not recruiters.matches(None, ["Hays"])
    assert recruiters.matches("Randstad Deutschland GmbH & Co. KG", ["Randstad"])


def test_adding_tags_stored_jobs_at_once_and_new_jobs_on_insert(conn):
    old = _job(conn, 1, "Hays AG")
    other = _job(conn, 2, "ACME")
    cleared = _job(conn, 3, "Hays Talent Solutions")
    recruiters.clear(conn, cleared)                                   # the user said: not a recruiter
    r = recruiters.add(conn, ["Hays", "hays", " "], note="agency")
    assert r["names"] == ["Hays"] and [j["id"] for j in r["tagged"]] == [old]
    assert (_via(conn, old), _via(conn, other), _via(conn, cleared)) == ("list", None, "cleared")
    new = _job(conn, 4, "HAYS")                                       # found in a later run
    assert _via(conn, new) == "list"
    with pytest.raises(ValueError, match="already on the list"):
        recruiters.add(conn, ["HAYS AG"])
    assert recruiters.list_recruiters(conn)[0]["jobs"] == 2
    assert recruiters.remove(conn, r["id"]) == 2 and _via(conn, old) is None


def test_recruiter_jobs_get_documents_only_on_request(conn):
    listed = _job(conn, 1, "Hays", "shortlisted", fit=90)
    recruiters.add(conn, ["Hays"])
    normal = _job(conn, 2, "ACME", "shortlisted", fit=80)
    detected = _job(conn, 3, "Talent GmbH", "new")
    jobs.evaluate_job(conn, detected, 85, **EVAL, via_recruiter=True, recruiter_reason="on behalf of our client")
    assert _via(conn, detected) == "detected"
    ids = lambda: [j["id"] for j in jobs.list_jobs(conn, "shortlisted", for_documents=True)]  # noqa: E731
    assert ids() == [normal]
    jobs.request_documents(conn, listed, "cv")
    assert set(ids()) == {listed, normal}
    recruiters.clear(conn, detected)                                  # "not a recruiter"
    assert set(ids()) == {listed, normal, detected}


def test_via_recruiter_needs_a_reason_and_keeps_a_list_tag(conn):
    jid = _job(conn, 1, "Hays")
    recruiters.add(conn, ["Hays"])
    with pytest.raises(ValueError, match="recruiter_reason"):
        jobs.evaluate_job(conn, jid, 70, **EVAL, via_recruiter=True)
    jobs.evaluate_job(conn, jid, 70, **EVAL, via_recruiter=True, recruiter_reason="agency")
    assert _via(conn, jid) == "list"


def test_render_documents_refuses_a_recruiter_job(conn):
    from mcp_server import server

    jid = _job(conn, 1, "Hays", "shortlisted", fit=90)
    recruiters.add(conn, ["Hays"])
    with pytest.raises(ToolError, match="via a recruiter"):
        server.render_documents(jid, "en", cv_content={"name": "x"})


def test_run_message_has_sections_and_a_recruiter_block(conn):
    run_id = runs.start_run(conn, "scheduled")
    normal, via = _job(conn, 1, "ACME"), _job(conn, 2, "Talent Partners")
    jobs.evaluate_job(conn, normal, 72, **EVAL)
    jobs.evaluate_job(conn, via, 80, **EVAL, via_recruiter=True, recruiter_reason="für unseren Kunden")
    run = runs.finish_run(conn, run_id)
    msg = notify.run_message(conn, run)
    assert msg.startswith("🔎 <b>Scheduled run</b>")
    assert "<b>⭐ Shortlisted, no documents yet (1)</b>\n• <b>Job 1</b>\n   ACME · Berlin · fit 72 · " in msg
    assert "<b>🤝 Via a recruiter (documents only on request) (1)</b>\n• <b>Job 2</b>" in msg
    assert "für unseren Kunden" in msg and msg.rstrip().endswith('">Open JobHunter</a>')


def test_reminders_go_out_once_with_both_links(conn, sent):
    jid = _job(conn, 1, "ACME")
    conn.execute("UPDATE jobs SET apply_email = 'jobs@acme.example', apply_method = 'email' WHERE id = ?", (jid,))
    assert reminders.set_reminder(conn, jid, "2026-10-30T09:00", "ask about the interview") == "2026-10-30 09:00"
    with pytest.raises(ValueError):
        reminders.set_reminder(conn, jid, "tomorrow")
    assert reminders.send_due(conn, now=datetime(2026, 10, 30, 8, 59)) == {"due": 0, "sent": 0}
    assert reminders.send_due(conn, now=datetime(2026, 10, 30, 9, 0)) == {"due": 1, "sent": 1}
    text = sent[-1]["text"]
    assert "⏰ <b>Reminder</b> · 30.10.2026 09:00" in text and "<b>Job 1</b> – ACME, Berlin" in text
    assert "ask about the interview" in text and 'href="http://localhost:5173/jobs/1"' in text
    assert 'href="mailto:jobs@acme.example?subject=' in text and 'href="https://x.example/1">The posting' in text
    assert reminders.send_due(conn, now=datetime(2026, 10, 31)) == {"due": 0, "sent": 0}   # once only


def test_a_failed_send_is_retried(conn, sent, monkeypatch):
    jid = _job(conn, 1)
    reminders.set_reminder(conn, jid, "2026-10-30 09:00")
    monkeypatch.setattr(notify, "send", lambda text, conn=None: "failed: offline")
    assert reminders.send_due(conn, now=datetime(2026, 10, 30, 10))["sent"] == 0
    monkeypatch.undo()
    monkeypatch.setattr(notify, "_config", lambda: ("token", "chat"))
    monkeypatch.setattr(notify, "_call", lambda method, token, **p: sent.append(p) or {})
    assert reminders.send_due(conn, now=datetime(2026, 10, 30, 10))["sent"] == 1
    assert 'href="https://x.example/1">Apply here' in sent[-1]["text"]
