"""Telegram notifications (CLAUDE.md §8). One-way; failures are logged, never raised into a run.

.env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (R3: the token never goes into logs, DB or messages).
"""

from __future__ import annotations

import html
import json
import os
import sqlite3
import sys

import httpx

from core.db import ROOT, get_settings

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000          # Telegram limit is 4096
MAX_ATTENTION_ITEMS = 10


def _config() -> tuple[str, str]:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _call(method: str, token: str, **params) -> dict:
    try:
        r = httpx.post(API.format(token=token, method=method), data=params, timeout=20)
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        # str(e) can contain the request URL, i.e. the token: report the type only
        raise RuntimeError(f"Telegram {method} failed ({type(e).__name__})") from None
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data.get('description', 'unknown error')}")
    return data["result"]


def send(text: str, conn: sqlite3.Connection | None = None) -> str:
    """Send one HTML message. Returns 'sent', 'disabled', 'not configured' or 'failed: …'."""
    if conn is not None and get_settings(conn).get("telegram_enabled", "1") != "1":
        return "disabled"
    token, chat_id = _config()
    if not token or not chat_id:
        return "not configured"
    if len(text) > MAX_LEN:
        text = text[:MAX_LEN - 2] + " …"
    try:
        _call("sendMessage", token, chat_id=chat_id, text=text, parse_mode="HTML",
              disable_web_page_preview="true")
        return "sent"
    except RuntimeError as e:
        print(f"[notify] {e}", file=sys.stderr)
        return f"failed: {e}"


def get_chat_ids() -> list[dict]:
    """For `cli.py telegram-setup`: chats that recently messaged the bot."""
    token, _ = _config()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")
    chats = {}
    for u in _call("getUpdates", token):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            chats[chat["id"]] = {"id": chat["id"], "type": chat.get("type"),
                                 "name": chat.get("username") or chat.get("title") or chat.get("first_name")}
    return list(chats.values())


# ── message composition ─────────────────────────────────────────────────────

def _e(s) -> str:
    return html.escape(str(s or ""), quote=False)


# Which messages are sent (settings, migration 011; telegram_enabled is the master switch).
EVENTS = ("notify_run_summary", "notify_docs_ready", "notify_evaluated", "notify_attention", "notify_failures")
MAX_LIST_ITEMS = 10
_DOC_LABELS = {("cv", "de"): "Lebenslauf", ("cv", "en"): "CV", ("cv", None): "CV",
               ("letter", "de"): "Anschreiben", ("letter", "en"): "Cover letter", ("letter", None): "Cover letter"}


def enabled(conn: sqlite3.Connection | None, event: str) -> bool:
    return conn is None or get_settings(conn).get(event, "1") == "1"


def _place(j: dict) -> str:
    place = ", ".join(_e(x) for x in (j.get("company"), j.get("location")) if x)
    return f" – {place}" if place else ""


def _documents(job_id: int) -> str:
    from core.applications import classify_document, list_documents

    labels = [_DOC_LABELS.get(classify_document(p.name) or ("cv", None), p.name) for p in list_documents(job_id)]
    return " + ".join(labels) or "documents"


def _capped(lines: list[str], items: list, render, more: str) -> None:
    lines.extend(render(j) for j in items[:MAX_LIST_ITEMS])
    if len(items) > MAX_LIST_ITEMS:
        lines.append(f"… and {len(items) - MAX_LIST_ITEMS} more: {more}")


def run_message(conn: sqlite3.Connection, run: dict, summary: str) -> str:
    """The message for a finished run, depending on its trigger and the notify_* settings:
    - scheduled/manual: summary line, motivation gaps, new shortlisted jobs without documents;
    - docs ("Generate now"): the documents written, and requested jobs still waiting;
    - single ("Evaluate now"): the job's fit score and decision;
    and for all: every job whose documents were written (with links), jobs that need the user,
    and source / run problems. Empty string if nothing is enabled or there is nothing to say."""
    from core.runs import (attention_jobs, evaluated_jobs, motivation_gaps, requested_waiting, source_problems,
                           written_jobs)

    since, until, trigger = run["started_at"], run.get("finished_at"), run.get("trigger") or "scheduled"
    base = get_settings(conn).get("ui_base_url", "http://localhost:5173").rstrip("/")
    link = lambda j: f"<a href=\"{base}/jobs/{j['id']}\">open</a>"  # noqa: E731
    fit = lambda j: f" (fit {j['fit_score']})" if j.get("fit_score") is not None else ""  # noqa: E731
    lines: list[str] = []
    written = written_jobs(conn, since, until)

    if trigger == "docs":
        if enabled(conn, "notify_docs_ready"):
            lines.append(f"✍️ Requested documents: {len(written)} written" if written
                         else "✍️ Requested documents: nothing was written this time")
    elif trigger == "single":
        if enabled(conn, "notify_evaluated"):
            for j in evaluated_jobs(conn, since, until):
                verdict = {"shortlisted": "shortlisted ✅", "skipped": "skipped"}.get(
                    j["decision"], f"scored (stays {j['decision'].replace('_', ' ')})")
                lines.append(f"🧮 <b>{_e(j['title'])}</b>{_place(j)}: fit {j['fit_score']} → {verdict} {link(j)}")
    elif enabled(conn, "notify_run_summary"):
        if trigger == "evaluate":
            scored = evaluated_jobs(conn, since, until)
            short = sum(j["decision"] == "shortlisted" for j in scored)
            left = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'new'").fetchone()[0]
            lines.append(f"🧮 Scored {len(scored)} waiting jobs · {short} shortlisted · "
                         f"{len(written)} docs ready · {left} still waiting")
        else:
            lines.append(_e(summary))
        gaps = motivation_gaps(conn, since)
        if gaps:
            lines.append("✍️ Add your motivation in profile.yaml for: " + ", ".join(_e(g) for g in gaps))
        # Worth a look, but below min_fit_for_documents: the user can press "Write docs".
        written_ids = {w["id"] for w in written}
        waiting = [j for j in evaluated_jobs(conn, since, until)
                   if j["decision"] == "shortlisted" and j["id"] not in written_ids and not j["docs_requested"]]
        if waiting:
            lines.append("⭐ Shortlisted, no documents yet:")
            _capped(lines, waiting, lambda j: f"• <b>{_e(j['title'])}</b>{_place(j)}{fit(j)} {link(j)}", f"{base}/?status=shortlisted")

    if written and enabled(conn, "notify_docs_ready"):
        if trigger != "docs":
            lines.append("📄 Documents ready:")
        def doc_line(j):
            extra = " · ✉️ email draft saved" if j["email_draft_saved"] else ""
            if j["status"] == "needs_attention":
                extra += " · ⚠️ approve the inferred facts first"
            return f"• <b>{_e(j['title'])}</b>{_place(j)}{fit(j)}: {_documents(j['id'])}{extra} {link(j)}"
        _capped(lines, written, doc_line, f"{base}/?status=docs_ready")
    if trigger == "docs" and enabled(conn, "notify_docs_ready"):
        left = requested_waiting(conn)
        if left:
            lines.append("⏳ Still waiting (next run or Generate now):")
            _capped(lines, left, lambda j: f"• <b>{_e(j['title'])}</b>{_place(j)} {link(j)}", base)

    if enabled(conn, "notify_attention"):
        written_ids = {w["id"] for w in written}
        jobs = [j for j in attention_jobs(conn, since, until) if j["id"] not in written_ids]  # already listed above
        review = [j for j in jobs if j["attention_reason"] == "alert_review"]
        jobs = [j for j in jobs if j["attention_reason"] != "alert_review"]
        _capped(lines, jobs, lambda j: f"⚠️ <b>{_e(j['title'])}</b>{_place(j)}: {_e(j['attention_reason'])} {link(j)}",
                f"{base}/attention")
        if review:  # one line, not one per job: these can be many
            lines.append(f"📥 {len(review)} job-alert jobs match no filter — pick the ones worth evaluating: "
                         f"<a href=\"{base}/attention#review\">review</a>")

    if enabled(conn, "notify_failures"):
        for p in source_problems(run):
            name = _e(p["source"].removeprefix("jobspy:"))
            if p["failed"] >= p["of"]:
                lines.append(f"❌ {name} failed this run (others OK)")
            elif p["soft"]:
                lines.append(f"⚠️ {name}: no results for {p['failed']} of {p['of']} filters")
            else:
                lines.append(f"⚠️ {name}: errors in {p['failed']} of {p['of']} filters")
        errors = run.get("errors") or []
        for e in json.loads(errors) if isinstance(errors, str) else errors:
            if e.get("source") == "run":
                lines.append(f"🛑 {_e(e.get('message'))}")
    return "\n".join(lines)


def notify_run_finished(conn: sqlite3.Connection, run: dict, summary: str) -> str:
    text = run_message(conn, run, summary)
    return send(text, conn) if text else "nothing to send"


def notify_run_failed(conn: sqlite3.Connection | None, reason: str, log_file: str | None = None) -> str:
    if not enabled(conn, "notify_failures"):
        return "disabled"
    text = f"🛑 Run failed: {_e(reason)}" + (f" — see {_e(log_file)}" if log_file else "")
    return send(text, conn)


def notify_run_refused(conn: sqlite3.Connection, trigger: str, reason: str) -> str:
    """A run the user started from the UI ("Generate now", "Evaluate now") couldn't start.
    Scheduled runs refused by the time guard stay quiet."""
    if not enabled(conn, "notify_failures"):
        return "disabled"
    what = {"docs": "Generate now", "single": "Evaluate now", "manual": "Run now",
            "evaluate": "Score waiting jobs"}.get(trigger, trigger)
    return send(f"⏸ {what} couldn't start: {_e(reason)}", conn)
