"""Follow-up reminders and the follow-up text (user request 2026-10-19)."""

import pytest

from core import db, followups, jobs, notify
from core.filters import seed_default_filters
from core.models import JobPosting
from core.profile import ProfileError, load_profile


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(notify, "_config", lambda: ("token", "chat"))
    monkeypatch.setattr(notify, "_call", lambda method, token, **p: out.append(p) or {})
    return out


@pytest.fixture
def conn(tmp_path, monkeypatch, sent):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "f.db"))
    c = db.connect()
    db.migrate(c)
    seed_default_filters(c)
    yield c
    c.close()


def _applied(conn, n, days_ago, title="Backend Developer (m/w/d)", language="de", via_dropdown=False):
    p = JobPosting(source="x", url=f"https://x.example/{n}", title=title, company="ACME GmbH", location="Mannheim",
                   canonical_url=f"x.example/{n}", fingerprint=f"fp{n}", description="…")
    p.status = "applied"
    jid = jobs.insert_job(conn, p)
    when = f"datetime('now', '-{days_ago} days')"
    conn.execute("UPDATE jobs SET language = ? WHERE id = ?", (language, jid))
    conn.execute(f"INSERT INTO status_history (job_id, from_status, to_status, changed_by, changed_at) "
                 f"VALUES (?, 'docs_ready', 'applied', 'user', {when})", (jid,))
    if not via_dropdown:
        conn.execute(f"INSERT INTO applications (job_id, applied_at) VALUES (?, {when})", (jid,))
    conn.commit()
    return jid


def test_due_reminders_and_each_is_sent_once(conn, sent):
    fresh = _applied(conn, 1, 3)
    follow = _applied(conn, 2, 15)
    dropdown = _applied(conn, 3, 20, via_dropdown=True)   # status set from the dropdown: date from history
    silent = _applied(conn, 4, 50)
    found = followups.due(conn)
    assert [j["id"] for j in found["follow_up"]] == [dropdown, follow]
    assert [j["id"] for j in found["no_response"]] == [silent]
    assert fresh not in [j["id"] for j in found["follow_up"] + found["no_response"]]

    r = followups.send_reminders(conn)
    assert r == {"follow_up": 2, "no_response": 1, "sent": "sent"} and len(sent) == 1
    text = sent[0]["text"]
    assert "📬 No reply after 14+ days" in text and "🔕 No reply for 42+ days" in text and "/jobs/" in text
    assert followups.send_reminders(conn)["sent"] == "nothing to send" and len(sent) == 1   # once only


def test_followed_up_stops_the_reminder_and_keeps_the_status(conn):
    jid = _applied(conn, 1, 20)
    followups.mark_followed_up(conn, jid)
    assert followups.due(conn)["follow_up"] == []
    assert jobs.get_job(conn, jid)["status"] == "applied"
    row = conn.execute("SELECT from_status, to_status, note FROM status_history WHERE job_id = ? ORDER BY id DESC", (jid,)).fetchone()
    assert tuple(row) == ("applied", "applied", "followed up")


def test_settings_switch_reminders_off(conn, sent):
    _applied(conn, 1, 20)
    conn.execute("UPDATE settings SET value = '0' WHERE key = 'notify_followups'")
    assert followups.send_reminders(conn)["sent"] == "disabled" and sent == []
    assert followups.due(conn)["follow_up"]                       # not marked: goes out when switched on
    conn.execute("UPDATE settings SET value = '0' WHERE key = 'followup_after_days'")
    assert followups.due(conn)["follow_up"] == []


def test_failed_telegram_marks_nothing(conn, monkeypatch):
    _applied(conn, 1, 20)
    monkeypatch.setattr(notify, "send", lambda text, conn=None: "failed: boom")
    assert followups.send_reminders(conn)["sent"] == "failed: boom"
    assert len(followups.due(conn)["follow_up"]) == 1


def test_followup_text_in_the_application_language(conn):
    de = next(j for j in followups.applied_jobs(conn) if j["id"] == _applied(conn, 1, 15))
    t = followups.followup_text(de, "Alex Beispiel")
    assert t["language"] == "de" and t["subject"] == "Nachfrage zu meiner Bewerbung als Backend Developer"
    assert "(m/w/d)" not in t["body"] and t["body"].endswith("Mit freundlichen Grüßen\nAlex Beispiel")
    en = next(j for j in followups.applied_jobs(conn) if j["id"] == _applied(conn, 2, 15, "Data Engineer (all genders)", "en"))
    t = followups.followup_text(en, "Alex Beispiel")
    assert t["subject"] == "Follow-up on my application for Data Engineer" and "at ACME GmbH" in t["body"]


def test_check_profile_reports_errors(tmp_path):
    bad = tmp_path / "p.yaml"
    bad.write_text("personal: {name: X}\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="missing required section"):
        load_profile(bad)
