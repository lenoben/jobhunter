"""Follow-up reminders for applications without a reply (user request 2026-10-19).

- After `followup_after_days` (14) in status `applied` the user gets one Telegram reminder per
  application, with a ready follow-up text on the job page (`followup_text`).
- After `followup_no_response_days` (42) a second one suggests marking it rejected / withdrawn.
  The status is never changed here: only the user sets applied → rejected (CLAUDE.md §4).
- `cli.py followups --notify` sends them; run.ps1 calls it before every scheduled/manual run, so
  reminders also go out when the time guard refuses the run.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from core.db import get_settings

# The date the user applied: applications.applied_at ("Mark as applied"), else the first
# status change to applied (status set from the dropdown).
APPLIED_AT = """COALESCE(a.applied_at, (SELECT MIN(h.changed_at) FROM status_history h
                                         WHERE h.job_id = j.id AND h.to_status = 'applied'))"""


def _days(conn: sqlite3.Connection, key: str, default: int) -> int:
    try:
        return max(0, int(float(get_settings(conn).get(key, default))))
    except ValueError:
        return default


def applied_jobs(conn: sqlite3.Connection) -> list[dict]:
    """Jobs still waiting for a reply (status applied), oldest application first, with
    applied_at, days since, and the reminder state."""
    rows = conn.execute(
        f"""SELECT j.id, j.title, j.company, j.location, j.language, a.doc_language, {APPLIED_AT} AS applied_at,
                   a.followup_reminded_at, a.followed_up_at, a.no_response_reminded_at,
                   CAST(julianday('now') - julianday({APPLIED_AT}) AS INTEGER) AS days
            FROM jobs j LEFT JOIN applications a ON a.job_id = j.id
            WHERE j.status = 'applied' ORDER BY applied_at""").fetchall()
    return [dict(r) for r in rows if r["applied_at"]]


def due(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """{'follow_up': [...], 'no_response': [...]}: reminders not sent yet. A job that is due for
    both only gets the no-response one. 0 days = that reminder is off."""
    after, silent = _days(conn, "followup_after_days", 14), _days(conn, "followup_no_response_days", 42)
    out: dict[str, list[dict]] = {"follow_up": [], "no_response": []}
    for j in applied_jobs(conn):
        if silent and j["days"] >= silent and not j["no_response_reminded_at"]:
            out["no_response"].append(j)
        elif after and j["days"] >= after and not j["followup_reminded_at"] and not j["followed_up_at"] \
                and not (silent and j["days"] >= silent):
            out["follow_up"].append(j)
    return out


def _mark(conn: sqlite3.Connection, job_id: int, column: str, applied_at: str | None = None) -> None:
    assert column in ("followup_reminded_at", "followed_up_at", "no_response_reminded_at")
    conn.execute(f"""INSERT INTO applications (job_id, applied_at, {column}) VALUES (?, ?, datetime('now'))
                     ON CONFLICT(job_id) DO UPDATE SET {column} = datetime('now')""", (job_id, applied_at))


def mark_followed_up(conn: sqlite3.Connection, job_id: int, note: str | None = None) -> None:
    """The user sent a follow-up: no more follow-up reminder; shows in the history (status unchanged)."""
    job = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        raise ValueError(f"job {job_id} not found")
    _mark(conn, job_id, "followed_up_at")
    conn.execute("INSERT INTO status_history (job_id, from_status, to_status, note, changed_by) VALUES (?, ?, ?, ?, 'user')",
                 (job_id, job["status"], job["status"], f"followed up{': ' + note if note else ''}"))
    conn.commit()


def _clean_title(title: str) -> str:
    return re.sub(r"\s*\((?:m|w|d|f|x|div|all genders?|gn\*?)(?:\s*[/|,]\s*(?:m|w|d|f|x|div))*\)\s*", " ",
                  title or "", flags=re.IGNORECASE).strip()


def _date(applied_at: str, lang: str) -> str:
    d = datetime.fromisoformat(applied_at[:19])
    return d.strftime("%d.%m.%Y") if lang == "de" else f"{d.day} {d.strftime('%B %Y')}"


def followup_text(job: dict, name: str) -> dict:
    """{subject, body, language}: a short, polite follow-up in the application's language. Uses only
    the job title, company, application date and the user's name (R5: nothing invented)."""
    lang = job.get("doc_language") or job.get("language") or "de"
    lang = lang if lang in ("de", "en") else "de"
    title, date = _clean_title(job["title"]), _date(job["applied_at"], lang)
    if lang == "de":
        subject = f"Nachfrage zu meiner Bewerbung als {title}"
        body = (f"Sehr geehrte Damen und Herren,\n\n"
                f"am {date} habe ich mich bei Ihnen als {title} beworben. Ich möchte freundlich nachfragen, "
                f"ob Sie mir bereits einen Zwischenstand zum Auswahlverfahren nennen können.\n\n"
                f"Die Stelle interessiert mich weiterhin sehr. Für Rückfragen oder ein persönliches Gespräch "
                f"stehe ich Ihnen gern zur Verfügung.\n\nMit freundlichen Grüßen\n{name}")
    else:
        subject = f"Follow-up on my application for {title}"
        body = (f"Dear Hiring Team,\n\n"
                f"on {date} I applied for the {title} position{' at ' + job['company'] if job.get('company') else ''}. "
                f"I would like to kindly ask whether there is any update on the selection process.\n\n"
                f"I am still very interested in the role and happy to answer any questions or arrange a call.\n\n"
                f"Kind regards\n{name}")
    return {"subject": subject, "body": body, "language": lang}


def reminder_message(conn: sqlite3.Connection, found: dict[str, list[dict]]) -> str:
    from core.notify import _e, _place

    base = get_settings(conn).get("ui_base_url", "http://localhost:5173").rstrip("/")
    after, silent = _days(conn, "followup_after_days", 14), _days(conn, "followup_no_response_days", 42)
    item = lambda j: (f"• <b>{_e(j['title'])}</b>{_place(j)} · applied {_date(j['applied_at'], 'de')} "  # noqa: E731
                      f"({j['days']} days) · <a href=\"{base}/jobs/{j['id']}\">open</a>")
    lines: list[str] = []
    if found["follow_up"]:
        lines.append(f"📬 No reply after {after}+ days: time to follow up (the text is ready on the job page)")
        lines += [item(j) for j in found["follow_up"]]
    if found["no_response"]:
        lines.append(f"🔕 No reply for {silent}+ days: mark as rejected or withdrawn?")
        lines += [item(j) for j in found["no_response"]]
    return "\n".join(lines)


def send_reminders(conn: sqlite3.Connection, dry_run: bool = False) -> dict:
    """Send the due reminders in one Telegram message and remember them, so each goes out once.
    If Telegram is off or fails, nothing is marked and they go out next time."""
    from core import notify

    found = due(conn)
    count = len(found["follow_up"]) + len(found["no_response"])
    if not count or dry_run:
        return {"follow_up": len(found["follow_up"]), "no_response": len(found["no_response"]), "sent": "nothing to send" if not count else "dry run"}
    if not notify.enabled(conn, "notify_followups"):
        return {"follow_up": len(found["follow_up"]), "no_response": len(found["no_response"]), "sent": "disabled"}
    result = notify.send(reminder_message(conn, found), conn)
    if result == "sent":
        for j in found["follow_up"]:
            _mark(conn, j["id"], "followup_reminded_at", j["applied_at"])
        for j in found["no_response"]:
            _mark(conn, j["id"], "no_response_reminded_at", j["applied_at"])
        conn.commit()
    return {"follow_up": len(found["follow_up"]), "no_response": len(found["no_response"]), "sent": result}
