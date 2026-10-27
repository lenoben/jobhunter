"""Reminders per job (user request 2026-10-28, core §16c).

The user sets a date and time (and an optional note) on the job page. `cli.py reminders --notify`
runs every 15 minutes (scheduled task "JobHunter reminders", setup-task.ps1; no LLM) and sends one
Telegram message per due reminder: the job title, its JobHunter link, and where to apply (the link,
or the email address as a mailto link). remind_at is the PC's local time 'YYYY-MM-DD HH:MM', like
the UI's date/time input; reminded_at is set only after Telegram accepted the message, so a
reminder that couldn't be sent goes out on the next check.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from urllib.parse import quote

from core.db import get_settings

_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}$")


def normalize_at(value: str) -> str:
    """'2026-10-30T09:00' / '2026-10-30 09:00' → '2026-10-30 09:00' (validated)."""
    v = (value or "").strip()
    if not _AT_RE.match(v):
        raise ValueError("the reminder needs a date and time (YYYY-MM-DD HH:MM)")
    v = v.replace("T", " ")
    datetime.strptime(v, "%Y-%m-%d %H:%M")
    return v


def set_reminder(conn: sqlite3.Connection, job_id: int, at: str, note: str | None = None) -> str:
    at = normalize_at(at)
    if conn.execute("""UPDATE jobs SET remind_at = ?, remind_note = ?, reminded_at = NULL WHERE id = ?""",
                    (at, (note or "").strip()[:500] or None, job_id)).rowcount == 0:
        raise ValueError(f"job {job_id} not found")
    conn.commit()
    return at


def clear_reminder(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("UPDATE jobs SET remind_at = NULL, remind_note = NULL, reminded_at = NULL WHERE id = ?", (job_id,))
    conn.commit()


def due(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    now_s = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    return [dict(r) for r in conn.execute(
        """SELECT id, title, company, location, language, url, apply_url, apply_email, status, remind_at, remind_note
           FROM jobs WHERE remind_at IS NOT NULL AND reminded_at IS NULL AND remind_at <= ?
           ORDER BY remind_at""", (now_s,))]


def message(conn: sqlite3.Connection, j: dict) -> str:
    from core.notify import _e, _place, link

    base = get_settings(conn).get("ui_base_url", "http://localhost:5173").rstrip("/")
    when = datetime.strptime(j["remind_at"], "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M")
    lines = [f"⏰ <b>Reminder</b> · {_e(when)}", "", f"<b>{_e(j['title'])}</b>{_place(j)}"]
    if j.get("remind_note"):
        lines.append(f"📝 {_e(j['remind_note'])}")
    lines.append("")
    lines.append(f"🔎 {link(f'{base}/jobs/{j['id']}', 'Open in JobHunter')}")
    if j.get("apply_email"):
        subject = quote(f"Bewerbung als {j['title']}" if j.get("language") == "de" else f"Application: {j['title']}")
        lines.append(f"✉️ {link(f'mailto:{j['apply_email']}?subject={subject}', 'Write an email')} · "
                     f"<code>{_e(j['apply_email'])}</code>")
    apply = j.get("apply_url") or j.get("url")
    if apply and not (j.get("apply_email") and not j.get("apply_url")):
        lines.append(f"📝 {link(apply, 'Apply here')}")
    elif j.get("url"):
        lines.append(f"📄 {link(j['url'], 'The posting')}")
    return "\n".join(lines)


def send_due(conn: sqlite3.Connection, now: datetime | None = None, dry_run: bool = False) -> dict:
    from core import notify

    found = due(conn, now)
    if not found or dry_run:
        return {"due": len(found), "sent": 0}
    if not notify.enabled(conn, "notify_reminders"):
        return {"due": len(found), "sent": 0, "result": "disabled"}
    sent = 0
    for j in found:
        if notify.send(message(conn, j), conn) == "sent":
            conn.execute("UPDATE jobs SET reminded_at = datetime('now') WHERE id = ?", (j["id"],))
            conn.execute("""INSERT INTO status_history (job_id, from_status, to_status, note, changed_by)
                            VALUES (?, ?, ?, ?, 'user')""",
                         (j["id"], j["status"], j["status"], f"reminder sent ({j['remind_at']})"))
            conn.commit()
            sent += 1
    return {"due": len(found), "sent": sent}
