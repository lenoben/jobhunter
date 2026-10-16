"""Run bookkeeping: the time guard for start_run, per-source errors, and closing a run."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from core.db import get_settings

# A run still "running" after this long died without finish_run (the scheduled task is killed
# after 2 h, CLAUDE.md §9); it is closed as failed so it doesn't block every later run.
STALE_AFTER = timedelta(hours=3)
TRIGGERS = ("scheduled", "manual", "docs", "single", "evaluate")
# "single": the user added a job / its full posting and pressed "evaluate now": one job only.
# "evaluate": "Score waiting jobs" — evaluates the backlog of new jobs (no search), then the writer
# stage writes documents for the ones that qualify.
QUICK_TRIGGERS = ("docs", "single", "evaluate")
# "docs": user clicked "Generate now" — only the writer stage, only for jobs the user requested
# documents for. Small, so it skips min_hours_between_runs and doesn't count for it either; it is
# still never started while another run is running.


class RunRefused(Exception):
    pass


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)  # SQLite datetime('now') is UTC


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_run(conn: sqlite3.Connection, trigger: str) -> int:
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger must be one of {', '.join(TRIGGERS)}")
    min_hours = float(get_settings(conn).get("min_hours_between_runs", "4"))
    now = _now()

    for r in conn.execute("SELECT id, started_at FROM runs WHERE status = 'running'").fetchall():
        if now - _parse(r["started_at"]) > STALE_AFTER:
            add_errors(conn, r["id"], [{"source": "run", "message": "never finished (stale); closed by start_run"}])
            conn.execute("UPDATE runs SET status = 'failed', finished_at = datetime('now') WHERE id = ?", (r["id"],))
        else:
            raise RunRefused(f"run {r['id']} is still running (started {r['started_at']} UTC)")

    last = conn.execute(
        "SELECT id, finished_at FROM runs WHERE finished_at IS NOT NULL AND status != 'failed' "
        "AND trigger NOT IN ('docs', 'single', 'evaluate') ORDER BY finished_at DESC LIMIT 1").fetchone()
    if last and trigger not in QUICK_TRIGGERS:
        since = now - _parse(last["finished_at"])
        if since < timedelta(hours=min_hours):
            wait = timedelta(hours=min_hours) - since
            raise RunRefused(f"run {last['id']} finished {since.total_seconds() / 3600:.1f} h ago; "
                             f"min_hours_between_runs is {min_hours:g} (next run possible in "
                             f"{wait.total_seconds() / 60:.0f} min)")

    cur = conn.execute("INSERT INTO runs (trigger) VALUES (?)", (trigger,))
    conn.commit()
    if trigger in ("scheduled", "manual"):  # automatic clean-up of old jobs (job_retention_days)
        from core.jobs import purge_old_jobs
        purge_old_jobs(conn)
    return cur.lastrowid


def current_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM runs WHERE status = 'running' ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"] if row else None


def get_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise ValueError(f"run {run_id} not found")
    return row


def add_errors(conn: sqlite3.Connection, run_id: int, errors: list[dict]) -> None:
    if not errors:
        return
    current = json.loads(get_run(conn, run_id)["errors"] or "[]")
    current.extend({k: v for k, v in (("source", e.get("source", "?")), ("message", e.get("message", "")),
                                      ("filter_id", e.get("filter_id"))) if v is not None} for e in errors)
    conn.execute("UPDATE runs SET errors = ? WHERE id = ?", (json.dumps(current, ensure_ascii=False), run_id))


def add_counts(conn: sqlite3.Connection, run_id: int, found: int = 0, new_jobs: int = 0) -> None:
    conn.execute("UPDATE runs SET found = found + ?, new_jobs = new_jobs + ? WHERE id = ?",
                 (found, new_jobs, run_id))


def add_searches(conn: sqlite3.Connection, run_id: int, keys: list[str]) -> None:
    """Count one search per source key (e.g. 'arbeitnow', 'jobspy:linkedin') for this run."""
    counts = json.loads(get_run(conn, run_id)["source_searches"] or "{}")
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    conn.execute("UPDATE runs SET source_searches = ? WHERE id = ?", (json.dumps(counts), run_id))


SOFT_ERROR = "returned no results"  # a site gave 0 postings: blocked, or simply nothing matching


def source_problems(run: dict) -> list[dict]:
    """Errors per source with how many of its searches were affected:
    [{source, failed, of, soft, message}]. soft = only "no results", no real error.
    'run' errors (failed_reason) are not included."""
    searches = run.get("source_searches")
    searches = json.loads(searches) if isinstance(searches, str) else (searches or {})
    errors = run.get("errors")
    errors = json.loads(errors) if isinstance(errors, str) else (errors or [])
    out: dict[str, dict] = {}
    for i, e in enumerate(errors):
        src = e.get("source") or "?"
        if src == "run":
            continue
        p = out.setdefault(src, {"source": src, "searches": set(), "soft": True, "message": e.get("message", "")})
        # one source can log several errors in one filter search (BA: one per keyword)
        p["searches"].add(e.get("filter_id", f"#{i}"))
        if not str(e.get("message", "")).startswith(SOFT_ERROR):
            p["soft"], p["message"] = False, e.get("message", "")
    for p in out.values():
        p["failed"] = len(p.pop("searches"))
        p["of"] = max(searches.get(p["source"], 0), p["failed"])
    return sorted(out.values(), key=lambda p: p["source"])


def run_status(run: dict, failed_reason: str | None) -> str:
    """failed: the run couldn't work. partial: a real error, or a source gave nothing in ALL its
    searches. ok: otherwise — a site with no results for some filters is normal (LinkedIn)."""
    if failed_reason:
        return "failed"
    problems = source_problems(run)
    return "partial" if any(not p["soft"] or p["failed"] >= p["of"] for p in problems) else "ok"


def attention_jobs(conn: sqlite3.Connection, since: str, until: str | None = None) -> list[dict]:
    """Jobs moved to needs_attention since `since` (UTC) that are still waiting for the user."""
    return [dict(r) for r in conn.execute(
        """SELECT DISTINCT j.id, j.title, j.company, j.location, j.attention_reason
           FROM status_history h JOIN jobs j ON j.id = h.job_id
           WHERE h.to_status = 'needs_attention' AND h.from_status IS NOT h.to_status AND h.changed_at >= ? AND h.changed_at <= COALESCE(?, '9999')
             AND j.status = 'needs_attention'
           ORDER BY j.id""", (since, until))]


def tailored_since(conn: sqlite3.Connection, since: str) -> int:
    """Jobs whose documents became ready to use since `since`. Documents waiting for the user to
    approve inferred facts are counted under needs_you instead."""
    return conn.execute(
        """SELECT COUNT(DISTINCT job_id) FROM status_history
           WHERE changed_at >= ? AND changed_by = 'claude' AND to_status = 'docs_ready'
             AND from_status IS NOT to_status""",
        (since,)).fetchone()[0]


def written_jobs(conn: sqlite3.Connection, since: str, until: str | None = None) -> list[dict]:
    """Jobs whose documents were written since `since`: docs_ready, or waiting for the user to
    approve inferred facts (needs_attention / inferred_facts)."""
    return [dict(r) for r in conn.execute(
        """SELECT DISTINCT j.id, j.title, j.company, j.location, j.fit_score, j.status, j.attention_reason,
                  COALESCE(a.email_draft_saved, 0) AS email_draft_saved
           FROM status_history h JOIN jobs j ON j.id = h.job_id LEFT JOIN applications a ON a.job_id = j.id
           WHERE h.changed_at >= ? AND h.changed_at <= COALESCE(?, '9999') AND h.changed_by = 'claude'
             AND h.from_status IS NOT h.to_status AND (h.to_status = 'docs_ready'
                  OR (h.to_status = 'needs_attention' AND j.attention_reason = 'inferred_facts'))
           ORDER BY j.id""", (since, until))]


def evaluated_jobs(conn: sqlite3.Connection, since: str, until: str | None = None) -> list[dict]:
    """Jobs Claude evaluated since `since` (new → shortlisted / skipped), best fit first."""
    return [dict(r) for r in conn.execute(
        """SELECT DISTINCT j.id, j.title, j.company, j.location, j.fit_score, h.to_status AS decision,
                  j.docs_requested
           FROM status_history h JOIN jobs j ON j.id = h.job_id
           WHERE h.changed_at >= ? AND h.changed_at <= COALESCE(?, '9999') AND h.changed_by = 'claude'
             AND ((h.from_status = 'new' AND h.to_status IN ('shortlisted', 'skipped'))
                  OR h.note LIKE 'scored: fit %')
           ORDER BY j.fit_score IS NULL, j.fit_score DESC, j.id""", (since, until))]


def requested_waiting(conn: sqlite3.Connection) -> list[dict]:
    """Jobs the user requested documents for that still have none (e.g. over the per-run cap)."""
    return [dict(r) for r in conn.execute(
        """SELECT id, title, company FROM jobs WHERE status = 'shortlisted' AND docs_requested IS NOT NULL
           ORDER BY id""")]


MOTIVATION_GAP_RE = re.compile(r'Motivation for "([^"]+)"')


def motivation_gaps(conn: sqlite3.Connection, since: str) -> list[str]:
    """Filter categories whose motivation the writer found missing/thin in profile.yaml during this
    run (marked in the application summary, §7 rule 2) — for the Telegram summary."""
    rows = conn.execute(
        """SELECT DISTINCT a.summary FROM applications a JOIN status_history h ON h.job_id = a.job_id
           WHERE h.changed_at >= ? AND h.changed_by = 'claude' AND a.summary LIKE '%Motivation for "%'""",
        (since,))
    return sorted({m for (summary,) in rows for m in MOTIVATION_GAP_RE.findall(summary)})


def still_running_since(conn: sqlite3.Connection, since: str) -> list[int]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM runs WHERE status = 'running' AND started_at >= ?", (since,))]


def fail_open_runs(conn: sqlite3.Connection, reason: str) -> list[int]:
    """Close every run still marked running as failed (used after claude exited abnormally)."""
    ids = [r["id"] for r in conn.execute("SELECT id FROM runs WHERE status = 'running'")]
    for run_id in ids:
        add_errors(conn, run_id, [{"source": "run", "message": reason}])
        conn.execute("UPDATE runs SET status = 'failed', finished_at = datetime('now') WHERE id = ?", (run_id,))
    conn.commit()
    return ids


def finish_run(conn: sqlite3.Connection, run_id: int, tailored: int | None = None, needs_you: int | None = None,
               found: int | None = None, new_jobs: int | None = None,
               failed_reason: str | None = None) -> dict:
    """Close a running run. Counts default to what the DB recorded during the run
    (found/new_jobs from search_jobs, tailored and needs_you from status_history)."""
    run = get_run(conn, run_id)
    if run["status"] != "running":
        raise ValueError(f"run {run_id} is already closed (status {run['status']})")
    if tailored is None:
        tailored = tailored_since(conn, run["started_at"])
    if needs_you is None:  # alert jobs waiting for review are listed separately (one Telegram line)
        needs_you = sum(j["attention_reason"] != "alert_review" for j in attention_jobs(conn, run["started_at"]))
    if failed_reason:
        add_errors(conn, run_id, [{"source": "run", "message": failed_reason}])
    current = dict(get_run(conn, run_id))
    errors = json.loads(current["errors"] or "[]")
    status = run_status(current, failed_reason)
    conn.execute(
        "UPDATE runs SET finished_at = datetime('now'), status = ?, tailored = ?, needs_you = ?, "
        "found = COALESCE(?, found), new_jobs = COALESCE(?, new_jobs) WHERE id = ?",
        (status, tailored, needs_you, found, new_jobs, run_id))
    conn.commit()
    return dict(get_run(conn, run_id)) | {"errors": errors}


def summary_line(run: dict) -> str:
    """The Telegram run summary from CLAUDE.md §8, e.g. '🔎 Run 08:02 — 23 found · 6 new · …'."""
    started = _parse(run["started_at"]).astimezone()  # local time for the user
    return (f"🔎 Run {started:%H:%M} — {run['found']} found · {run['new_jobs']} new · "
            f"{run['tailored']} docs ready · {run['needs_you']} need you")
