"""Telegram notifications (CLAUDE.md §8). One-way; failures are logged, never raised into a run.

.env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (R3: the token never goes into logs, DB or messages).
"""

from __future__ import annotations

import html
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


def run_message(conn: sqlite3.Connection, run: dict, summary: str) -> str:
    """Summary line, failed sources, and the jobs that need the user (with UI links)."""
    from core.runs import attention_jobs, motivation_gaps, source_problems

    lines = [_e(summary)]
    gaps = motivation_gaps(conn, run["started_at"])
    if gaps:
        lines.append("✍️ Add your motivation in profile.yaml for: " + ", ".join(_e(g) for g in gaps))
    for p in source_problems(run):
        name = _e(p["source"].removeprefix("jobspy:"))
        if p["failed"] >= p["of"]:
            lines.append(f"❌ {name} failed this run (others OK)")
        elif p["soft"]:
            lines.append(f"⚠️ {name}: no results for {p['failed']} of {p['of']} filters")
        else:
            lines.append(f"⚠️ {name}: errors in {p['failed']} of {p['of']} filters")
    for e in run.get("errors") or []:
        if e.get("source") == "run":
            lines.append(f"🛑 {_e(e.get('message'))}")

    base = get_settings(conn).get("ui_base_url", "http://localhost:5173").rstrip("/")
    jobs = attention_jobs(conn, run["started_at"])
    for j in jobs[:MAX_ATTENTION_ITEMS]:
        place = ", ".join(_e(x) for x in (j["company"], j["location"]) if x)
        lines.append(f"⚠️ <b>{_e(j['title'])}</b> – {place}: {_e(j['attention_reason'])} "
                     f"<a href=\"{base}/jobs/{j['id']}\">open</a>")
    if len(jobs) > MAX_ATTENTION_ITEMS:
        lines.append(f"… and {len(jobs) - MAX_ATTENTION_ITEMS} more: {base}/attention")
    return "\n".join(lines)


def notify_run_finished(conn: sqlite3.Connection, run: dict, summary: str) -> str:
    return send(run_message(conn, run, summary), conn)


def notify_run_failed(conn: sqlite3.Connection | None, reason: str, log_file: str | None = None) -> str:
    text = f"🛑 Run failed: {_e(reason)}" + (f" — see {_e(log_file)}" if log_file else "")
    return send(text, conn)
