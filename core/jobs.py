"""Job rows and status history. Every status change writes status_history (CLAUDE.md §4)."""

from __future__ import annotations

import json
import re
import sqlite3

from core.db import get_settings
from core.dedup import canonical_url
from core.models import ATTENTION_REASONS, JOB_STATUSES, USER_ONLY_STATUSES, JobPosting

WORK_MODES = ("remote", "hybrid", "onsite", "unknown")
EMPLOYMENT_TYPES = ("full_time", "part_time", "minijob", "working_student", "internship",
                    "contract", "freelance", "unknown")
LANGUAGES = ("de", "en")
APPLY_METHODS = ("portal", "email", "external_ats", "unknown")
DECISIONS = ("skip", "shortlist")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

_INSERT_COLS = (
    "source", "source_job_id", "url", "canonical_url", "fingerprint", "title", "company", "location",
    "work_mode", "employment_type", "language", "salary_text", "salary_annual_eur", "salary_flag",
    "posted_at", "description", "apply_method", "apply_email", "status", "attention_reason", "filter_id",
)


def find_seen(conn: sqlite3.Connection, canonical: str, fp: str | None = None,
              include_deleted: bool = True) -> sqlite3.Row | dict | None:
    """R8: a job is seen if its canonical URL or its fingerprint already exists — also when the job
    was removed by the automatic clean-up ({id: None, status: 'deleted'})."""
    row = conn.execute("SELECT id, status FROM jobs WHERE canonical_url = ?", (canonical,)).fetchone()
    if row is None and fp:
        row = conn.execute("SELECT id, status FROM jobs WHERE fingerprint = ? LIMIT 1", (fp,)).fetchone()
    if row is None and include_deleted and conn.execute(
            "SELECT 1 FROM deleted_jobs WHERE canonical_url = ? OR (? IS NOT NULL AND fingerprint = ?)",
            (canonical, fp, fp)).fetchone():
        return {"id": None, "status": "deleted"}
    return row


def is_seen(conn: sqlite3.Connection, url: str) -> dict:
    row = find_seen(conn, canonical_url(url))
    return {"seen": True, "job_id": row["id"], "status": row["status"]} if row else {"seen": False}


# Jobs the user never acted on: no documents/application, not a favourite, no documents requested.
_PURGEABLE = """status IN ('new', 'skipped', 'shortlisted', 'needs_attention') AND favorite = 0
                AND docs_requested IS NULL AND id NOT IN (SELECT job_id FROM applications)
                AND updated_at < datetime('now', ?)"""


def purge_old_jobs(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Automatic clean-up (setting job_retention_days, 0 = off, user request 2026-10-18): delete
    jobs untouched for that many days that the user never acted on. Applied/interview/offer/
    rejected/withdrawn, documents, favourites and requested documents are always kept. The dedup
    keys stay in deleted_jobs, so a deleted job is never processed again (R8)."""
    days = int(float(get_settings(conn).get("job_retention_days", "0") or 0))
    if days <= 0:
        return 0
    age = f"-{days} days"
    if dry_run:
        return conn.execute(f"SELECT COUNT(*) FROM jobs WHERE {_PURGEABLE}", (age,)).fetchone()[0]
    conn.execute(f"""INSERT OR IGNORE INTO deleted_jobs (canonical_url, fingerprint)
                     SELECT canonical_url, fingerprint FROM jobs WHERE {_PURGEABLE}""", (age,))
    n = conn.execute(f"DELETE FROM jobs WHERE {_PURGEABLE}", (age,)).rowcount
    conn.commit()
    return n


def insert_job(conn: sqlite3.Connection, p: JobPosting, note: str | None = None) -> int:
    values = {c: getattr(p, c) for c in _INSERT_COLS}
    cur = conn.execute(
        f"INSERT INTO jobs ({', '.join(_INSERT_COLS)}) VALUES ({', '.join('?' * len(_INSERT_COLS))})",
        tuple(values.values()),
    )
    job_id = cur.lastrowid
    conn.execute(
        "INSERT INTO status_history (job_id, from_status, to_status, note, changed_by) VALUES (?, NULL, ?, ?, 'claude')",
        (job_id, p.status, note),
    )
    return job_id


def get_job(conn: sqlite3.Connection, job_id: int) -> dict:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"job {job_id} not found")
    job = dict(row)
    job["project_suggestions"] = json.loads(job.get("project_suggestions") or "[]")
    return job


DOC_REQUESTS = ("both", "cv", "letter", "motivation")  # motivation = Motivationsschreiben, on request only
DEFAULT_DOCUMENTS = ("cv", "both")


def documents_to_write(conn: sqlite3.Connection, docs_requested: str | None) -> str:
    """What the writer stage writes for a job: the user's per-job choice, else the setting
    default_documents ('cv' = CV only unless the user changed it)."""
    if docs_requested in DOC_REQUESTS:
        return docs_requested
    default = get_settings(conn).get("default_documents", "cv")
    return default if default in DEFAULT_DOCUMENTS else "cv"
# Statuses from which the user can ask for documents ("Apply anyway" / "Write documents").
REQUESTABLE_FROM = ("new", "skipped", "shortlisted", "needs_attention", "docs_ready")


def list_jobs(conn: sqlite3.Connection, status: str, limit: int = 50, for_documents: bool = False) -> list[dict]:
    """for_documents (writer stage): shortlisted jobs with fit ≥ min_fit_for_documents, or that the
    user asked documents for (docs_requested) — requested first, then by fit score. Each row has
    `documents` (cv | letter | both | motivation): what to write (documents_to_write)."""
    if status not in JOB_STATUSES:
        raise ValueError(f"status must be one of {', '.join(JOB_STATUSES)}")
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    cols = """id, title, company, location, status, attention_reason, fit_score, salary_flag, work_mode,
              language, apply_method, docs_requested, posted_at, first_seen_at"""
    if for_documents:
        if status != "shortlisted":
            raise ValueError("for_documents only works with status 'shortlisted'")
        threshold = int(float(get_settings(conn).get("min_fit_for_documents", "60")))
        rows = [dict(r) for r in conn.execute(
            f"""SELECT {cols} FROM jobs
                WHERE status = 'shortlisted' AND (docs_requested IS NOT NULL OR fit_score >= ?)
                ORDER BY docs_requested IS NULL, fit_score DESC, first_seen_at LIMIT ?""", (threshold, limit))]
        for r in rows:
            r["documents"] = documents_to_write(conn, r["docs_requested"])
        return rows
    order = ("fit_score DESC, first_seen_at" if status == "shortlisted"
             else "COALESCE(posted_at, first_seen_at) DESC, id DESC")
    return [dict(r) for r in conn.execute(
        f"SELECT {cols} FROM jobs WHERE status = ? ORDER BY {order} LIMIT ?", (status, limit))]


def request_documents(conn: sqlite3.Connection, job_id: int, which: str = "both", changed_by: str = "user") -> None:
    """"Apply anyway" / "Write documents": the writer stage tailors this job regardless of its fit
    score. which = both | cv | letter | motivation (the Motivationsschreiben, only ever on request)."""
    _check_choice("which", which, DOC_REQUESTS)
    job = get_job(conn, job_id)
    if job["status"] not in REQUESTABLE_FROM:
        raise ValueError(f"job {job_id} has status {job['status']}; documents can't be requested for it")
    conn.execute("UPDATE jobs SET docs_requested = ?, updated_at = datetime('now') WHERE id = ?", (which, job_id))
    label = {"both": "CV + cover letter", "cv": "CV", "letter": "cover letter", "motivation": "Motivationsschreiben"}[which]
    set_status(conn, job_id, "shortlisted", changed_by, note=f"documents requested: {label}")
    conn.commit()


def _project_suggestions(value) -> str | None:
    """R11: [{title, scope, days, covers}] → JSON, validated."""
    if not value:
        return None
    if not isinstance(value, list) or len(value) > 6:
        raise ValueError("project_suggestions must be a list of at most 6 items")
    clean = []
    for i, p in enumerate(value):
        if not isinstance(p, dict) or not all(str(p.get(k) or "").strip() for k in ("title", "scope", "covers")):
            raise ValueError(f"project_suggestions[{i}] needs title, scope, days and covers")
        try:
            days = float(p.get("days"))
        except (TypeError, ValueError):
            raise ValueError(f"project_suggestions[{i}].days must be a number of days") from None
        clean.append({"title": str(p["title"]).strip(), "scope": str(p["scope"]).strip(),
                      "days": int(days) if days == int(days) else days, "covers": str(p["covers"]).strip()})
    return json.dumps(clean, ensure_ascii=False)


def history(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT from_status, to_status, note, changed_by, changed_at FROM status_history "
        "WHERE job_id = ? ORDER BY id", (job_id,))]


def evaluate_job(conn: sqlite3.Connection, job_id: int, fit_score: int, fit_notes: str, work_mode: str,
                 employment_type: str, language: str, apply_method: str, decision: str,
                 apply_email: str | None = None, project_suggestions: list | None = None) -> str:
    """Store Claude's evaluation of a `new` job and move it to shortlisted/skipped. Returns the new status.
    A job that has no fit score yet in another status (documents requested before it was evaluated,
    or a re-evaluation, user request 2026-10-18) gets its score and notes stored; its status stays."""
    job = get_job(conn, job_id)
    score_only = job["status"] != "new"
    if score_only and job["fit_score"] is not None:
        raise ValueError(f"job {job_id} has status {job['status']} and is already scored; only 'new' or "
                         "unscored jobs are evaluated (R8)")
    _check_choice("work_mode", work_mode, WORK_MODES)
    _check_choice("employment_type", employment_type, EMPLOYMENT_TYPES)
    _check_choice("language", language, LANGUAGES)
    _check_choice("apply_method", apply_method, APPLY_METHODS)
    _check_choice("decision", decision, DECISIONS)
    if not 0 <= fit_score <= 100:
        raise ValueError("fit_score must be between 0 and 100")
    if not fit_notes.strip():
        raise ValueError("fit_notes must not be empty")
    if apply_email and not _EMAIL_RE.fullmatch(apply_email.strip()):
        raise ValueError(f"apply_email is not an email address: {apply_email!r}")
    if not apply_email and job["apply_email"]:
        # set by the user or taken from the posting (core/manual.py): an evaluation doesn't drop it
        apply_email, apply_method = job["apply_email"], "email"
    if apply_method == "email" and not apply_email and decision == "shortlist":
        raise ValueError("apply_method is 'email' but no apply_email was given")
    if decision == "shortlist" and job["filter_id"] is not None and not score_only:
        row = conn.execute("SELECT min_fit_score FROM search_filters WHERE id = ?", (job["filter_id"],)).fetchone()
        if row and fit_score < row["min_fit_score"]:
            raise ValueError(f"fit_score {fit_score} is below the filter's min_fit_score "
                             f"{row['min_fit_score']}; use decision 'skip'")
    suggestions = _project_suggestions(project_suggestions)

    conn.execute(
        "UPDATE jobs SET fit_score = ?, fit_notes = ?, work_mode = ?, employment_type = ?, language = ?, "
        "apply_method = ?, apply_email = ?, project_suggestions = ?, updated_at = datetime('now') WHERE id = ?",
        (fit_score, fit_notes, work_mode, employment_type, language, apply_method,
         apply_email.strip() if apply_email else None, suggestions, job_id))
    if score_only:
        conn.execute("INSERT INTO status_history (job_id, from_status, to_status, note, changed_by) "
                     "VALUES (?, ?, ?, ?, 'claude')", (job_id, job["status"], job["status"], f"scored: fit {fit_score}"))
        conn.commit()
        return job["status"]
    to_status = "shortlisted" if decision == "shortlist" else "skipped"
    set_status(conn, job_id, to_status, "claude", note=f"fit score {fit_score}")
    conn.commit()
    return to_status


def flag_attention(conn: sqlite3.Connection, job_id: int, reason: str, detail: str) -> None:
    job = get_job(conn, job_id)
    _check_choice("reason", reason, ATTENTION_REASONS)
    if job["status"] in USER_ONLY_STATUSES:
        raise ValueError(f"job {job_id} has status {job['status']}, which only the user changes")
    set_status(conn, job_id, "needs_attention", "claude", note=f"{reason}: {detail}", attention_reason=reason)
    conn.commit()


def _check_choice(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)} (got {value!r})")


def set_status(conn: sqlite3.Connection, job_id: int, to_status: str, changed_by: str,
               note: str | None = None, attention_reason: str | None = None) -> None:
    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"job {job_id} not found")
    conn.execute(
        "UPDATE jobs SET status = ?, attention_reason = ?, updated_at = datetime('now') WHERE id = ?",
        (to_status, attention_reason if to_status == "needs_attention" else None, job_id),
    )
    conn.execute(
        "INSERT INTO status_history (job_id, from_status, to_status, note, changed_by) VALUES (?, ?, ?, ?, ?)",
        (job_id, row["status"], to_status, note, changed_by),
    )
