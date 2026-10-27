import pytest

from core import db, jobs, notify, runs
from core.models import JobPosting


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(notify, "_config", lambda: ("token", "chat"))
    monkeypatch.setattr(notify, "_call", lambda method, token, **p: out.append(p) or {})
    return out


@pytest.fixture
def conn(tmp_path, sent):
    c = db.connect(tmp_path / "n.db")
    db.migrate(c)
    yield c
    c.close()


def _job(conn, n, title, status="new", reason=None):
    p = JobPosting(source="x", url=f"https://x.example/{n}", title=title, company="Müller <GmbH>",
                   location="Mannheim", canonical_url=f"x.example/{n}", fingerprint=f"fp{n}")
    p.status, p.attention_reason = status, reason
    return jobs.insert_job(conn, p)


def test_run_message_lists_failures_and_attention(conn):
    run_id = runs.start_run(conn, "manual")
    runs.add_errors(conn, run_id, [{"source": "jobspy:linkedin", "message": "blocked"},
                                   {"source": "jobspy:linkedin", "message": "again"}])
    _job(conn, 1, "Backend Developer (m/w/d)", "needs_attention", "work_authorization")
    _job(conn, 2, "Fine job")
    conn.commit()
    run = runs.finish_run(conn, run_id)
    assert run["status"] == "partial" and run["needs_you"] == 1

    msg = notify.run_message(conn, run, runs.summary_line(run))
    assert msg.count("❌ linkedin failed this run (others OK)") == 1
    assert ("<b>⚠️ Needs you (1)</b>\n• <b>Backend Developer (m/w/d)</b>\n"
            "   Müller &lt;GmbH&gt; · Mannheim · work-permit question · ") in msg
    assert "<b>🛠 Problems</b>" in msg
    assert 'href="http://localhost:5173/jobs/1"' in msg and "Fine job" not in msg


def test_partial_no_results_is_a_warning_not_a_failure(conn):
    run_id = runs.start_run(conn, "scheduled")
    for fid in range(1, 7):  # 6 filters, each searched LinkedIn and BA once
        runs.add_searches(conn, run_id, ["jobspy:linkedin", "ba_jobsuche"])
    runs.add_errors(conn, run_id, [
        {"source": "jobspy:linkedin", "message": "returned no results (blocked or nothing new)", "filter_id": 2},
        {"source": "jobspy:linkedin", "message": "returned no results (blocked or nothing new)", "filter_id": 5},
        # BA logs one error per keyword: 3 errors in ONE filter search
        {"source": "ba_jobsuche", "message": "'Go Developer': HTTP 500", "filter_id": 1},
        {"source": "ba_jobsuche", "message": "'Rust': HTTP 500", "filter_id": 1},
        {"source": "ba_jobsuche", "message": "'C++': HTTP 500", "filter_id": 1},
    ])
    conn.commit()
    run = runs.finish_run(conn, run_id)
    msg = notify.run_message(conn, run, runs.summary_line(run))
    assert "⚠️ linkedin: no results for 2 of 6 filters" in msg
    assert "⚠️ ba_jobsuche: errors in 1 of 6 filters" in msg
    assert "❌" not in msg
    assert run["status"] == "partial"  # a real (non-"no results") error stays partial


def test_only_soft_gaps_keep_the_run_ok(conn):
    run_id = runs.start_run(conn, "scheduled")
    runs.add_searches(conn, run_id, ["jobspy:linkedin"] * 6)
    runs.add_errors(conn, run_id, [{"source": "jobspy:linkedin", "message": "returned no results", "filter_id": 3}])
    conn.commit()
    assert runs.finish_run(conn, run_id)["status"] == "ok"


def test_source_without_any_results_is_failed(conn):
    run_id = runs.start_run(conn, "scheduled")
    runs.add_searches(conn, run_id, ["jobspy:linkedin"] * 2)
    runs.add_errors(conn, run_id, [{"source": "jobspy:linkedin", "message": "returned no results", "filter_id": f}
                                   for f in (1, 2)])
    conn.commit()
    run = runs.finish_run(conn, run_id)
    assert run["status"] == "partial"
    assert "❌ linkedin failed this run (others OK)" in notify.run_message(conn, run, runs.summary_line(run))


def test_send_respects_setting_and_never_raises(conn, sent, monkeypatch):
    conn.execute("UPDATE settings SET value = '0' WHERE key = 'telegram_enabled'")
    assert notify.send("hi", conn) == "disabled" and sent == []
    conn.execute("UPDATE settings SET value = '1' WHERE key = 'telegram_enabled'")
    assert notify.send("hi", conn) == "sent" and sent[0]["parse_mode"] == "HTML"

    def boom(*a, **k):
        raise RuntimeError("Telegram sendMessage failed (ConnectError)")
    monkeypatch.setattr(notify, "_call", boom)
    assert notify.send("hi", conn).startswith("failed")


def test_fail_open_runs_and_check(conn):
    run_id = runs.start_run(conn, "scheduled")
    since = conn.execute("SELECT started_at FROM runs WHERE id = ?", (run_id,)).fetchone()[0]
    assert runs.still_running_since(conn, since) == [run_id]
    assert runs.fail_open_runs(conn, "claude exited with code 1") == [run_id]
    assert runs.get_run(conn, run_id)["status"] == "failed"
    assert runs.still_running_since(conn, since) == []
    assert runs.start_run(conn, "scheduled")  # a failed run doesn't block the next one


def test_list_jobs_orders(conn):
    a, b = _job(conn, 1, "A", "shortlisted"), _job(conn, 2, "B", "shortlisted")
    conn.execute("UPDATE jobs SET fit_score = CASE id WHEN ? THEN 70 ELSE 90 END", (a,))
    assert [j["id"] for j in jobs.list_jobs(conn, "shortlisted")] == [b, a]
    with pytest.raises(ValueError):
        jobs.list_jobs(conn, "bogus")
