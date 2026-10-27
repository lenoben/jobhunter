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


def bot_username(token: str) -> str:
    """For cli.py setup: checks the token (getMe) and returns the bot's @name."""
    return _call("getMe", token).get("username") or "your bot"


def send_with(token: str, chat_id: str, text: str) -> None:
    """For cli.py setup: one plain message with a token not yet in .env. Raises RuntimeError."""
    _call("sendMessage", token, chat_id=chat_id, text=text)


def get_chat_ids(token: str | None = None) -> list[dict]:
    """For `cli.py telegram-setup` and cli.py setup: chats that recently messaged the bot."""
    token = token or _config()[0]
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
               ("letter", "de"): "Anschreiben", ("letter", "en"): "Cover letter", ("letter", None): "Cover letter",
               ("motivation", "de"): "Motivationsschreiben", ("motivation", "en"): "Motivation letter",
               ("motivation", None): "Motivationsschreiben"}


def enabled(conn: sqlite3.Connection | None, event: str) -> bool:
    return conn is None or get_settings(conn).get(event, "1") == "1"


def _place(j: dict) -> str:
    place = ", ".join(_e(x) for x in (j.get("company"), j.get("location")) if x)
    return f" – {place}" if place else ""


def link(href: str, text: str) -> str:
    return f'<a href="{html.escape(href, quote=True)}">{_e(text)}</a>'


def _documents(job_id: int) -> str:
    from core.applications import classify_document, list_documents

    labels = [_DOC_LABELS.get(classify_document(p.name) or ("cv", None), p.name) for p in list_documents(job_id)]
    return " + ".join(labels) or "documents"


# Plain words for the attention reasons (core/models.py ATTENTION_REASONS).
REASONS = {"needs_login": "login needed", "captcha": "CAPTCHA", "form_unclear": "form unclear",
           "missing_profile_info": "profile info missing", "german_only_form": "German-only form",
           "source_error": "source error", "work_authorization": "work-permit question",
           "below_blue_card_threshold": "salary below the Blue Card threshold",
           "inferred_facts": "approve the inferred facts", "alert_review": "job alert to review"}
TRIGGERS = {"scheduled": "Scheduled run", "manual": "Run now", "evaluate": "Score waiting jobs",
            "docs": "Generate now", "single": "Evaluate now"}


def _section(lines: list[str], title: str, items: list, render, more: str | None = None) -> None:
    """A blank line, a bold heading with the count, then the entries (capped at MAX_LIST_ITEMS)."""
    if not items:
        return
    lines += ["", f"<b>{title} ({len(items)})</b>"]
    for j in items[:MAX_LIST_ITEMS]:
        lines.extend(render(j))
    if len(items) > MAX_LIST_ITEMS:
        lines.append(f"… and {len(items) - MAX_LIST_ITEMS} more" + (f" · {more}" if more else ""))


def run_message(conn: sqlite3.Connection, run: dict, summary: str = "") -> str:
    """The message for a finished run (user request 2026-10-28: clear sections instead of one long
    list). A header (what ran and when) with the counts, then one section per kind, each entry as
        • <b>Title</b>
           Company · City · fit 72 · … · open
    Sections, by trigger and the notify_* settings:
    - 📄 Documents ready (all triggers; docs runs also ⏳ still waiting);
    - 🧮 the job's score (single);
    - ⭐ Shortlisted, no documents yet · 🤝 Via a recruiter (documents only on request, core §16c) ·
      ✍️ motivation missing (scheduled / manual / evaluate);
    - ⚠️ Needs you, and one 📥 line for job-alert jobs;
    - 🛠 Problems: sources and the run itself;
    and a link to JobHunter. Empty string if nothing is enabled or there is nothing to say.
    `summary` (finish_run's line) is no longer used: the counts come from `run`."""
    from core.runs import (_parse, attention_jobs, evaluated_jobs, motivation_gaps, requested_waiting,
                           source_problems, written_jobs)

    since, until, trigger = run["started_at"], run.get("finished_at"), run.get("trigger") or "scheduled"
    base = get_settings(conn).get("ui_base_url", "http://localhost:5173").rstrip("/")

    def entry(j: dict, *extra: str) -> list[str]:
        meta = [_e(x) for x in (j.get("company"), j.get("location")) if x]
        if j.get("fit_score") is not None:
            meta.append(f"fit {j['fit_score']}")
        meta += [x for x in extra if x]
        return [f"• <b>{_e(j['title'])}</b>", "   " + " · ".join([*meta, link(f"{base}/jobs/{j['id']}", "open")])]

    written = written_jobs(conn, since, until)
    written_ids = {w["id"] for w in written}
    scored = evaluated_jobs(conn, since, until) if trigger != "docs" else []
    try:
        when = f" · {_parse(since).astimezone():%d.%m. %H:%M}"
    except (TypeError, ValueError):
        when = ""
    body: list[str] = []

    if trigger == "single":
        if enabled(conn, "notify_evaluated"):
            for j in scored:
                verdict = {"shortlisted": "shortlisted ✅", "skipped": "skipped"}.get(
                    j["decision"], f"scored, stays {j['decision'].replace('_', ' ')}")
                body += entry(j, verdict)
                if j.get("via_recruiter") in ("list", "detected"):
                    body.append(f"   🤝 via a recruiter: documents only on request ({_e(j.get('recruiter_reason'))})")
    elif trigger == "docs":
        if enabled(conn, "notify_docs_ready"):
            body.append(f"{len(written)} written" if written else "Nothing was written this time.")
    elif enabled(conn, "notify_run_summary"):
        if trigger == "evaluate":
            short = sum(j["decision"] == "shortlisted" for j in scored)
            left = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'new'").fetchone()[0]
            body.append(f"{len(scored)} scored · {short} shortlisted · {len(written)} docs ready · {left} still waiting")
        else:
            body.append(f"{run.get('found') or 0} found · {run.get('new_jobs') or 0} new · "
                        f"{run.get('tailored') or 0} docs ready · {run.get('needs_you') or 0} need you")

    if written and enabled(conn, "notify_docs_ready"):
        def doc_entry(j):
            return entry(j, _documents(j["id"]), "✉️ draft saved" if j["email_draft_saved"] else "",
                         "⚠️ approve the inferred facts first" if j["status"] == "needs_attention" else "")
        _section(body, "📄 Documents ready", written, doc_entry, link(f"{base}/?status=docs_ready", "all"))
    if trigger == "docs" and enabled(conn, "notify_docs_ready"):
        _section(body, "⏳ Still waiting (next run or Generate now)", requested_waiting(conn), entry)

    if trigger not in ("docs", "single") and enabled(conn, "notify_run_summary"):
        shortlisted = [j for j in scored if j["decision"] == "shortlisted" and j["id"] not in written_ids
                       and not j["docs_requested"]]
        via = [j for j in shortlisted if j.get("via_recruiter") in ("list", "detected")]
        rest = [j for j in shortlisted if j not in via]
        _section(body, "⭐ Shortlisted, no documents yet", rest, entry, link(f"{base}/?status=shortlisted", "all"))
        _section(body, "🤝 Via a recruiter (documents only on request)", via,
                 lambda j: entry(j, _e(j.get("recruiter_reason") or "")), link(f"{base}/?recruiter=1", "all"))
        gaps = motivation_gaps(conn, since)
        if gaps:
            body += ["", "<b>✍️ Motivation missing</b> in profile.yaml for: " + ", ".join(_e(g) for g in gaps)]

    if enabled(conn, "notify_attention"):
        found = [j for j in attention_jobs(conn, since, until) if j["id"] not in written_ids]  # listed above
        review = [j for j in found if j["attention_reason"] == "alert_review"]
        found = [j for j in found if j["attention_reason"] != "alert_review"]
        _section(body, "⚠️ Needs you", found,
                 lambda j: entry(j, _e(REASONS.get(j["attention_reason"], j["attention_reason"]))),
                 link(f"{base}/attention", "all"))
        if review:  # one line, not one per job: these can be many
            body += ["", f"📥 {len(review)} job-alert jobs match no filter: "
                         + link(f"{base}/attention#review", "pick the ones worth evaluating")]

    if enabled(conn, "notify_failures"):
        problems = []
        for p in source_problems(run):
            name = _e(p["source"].removeprefix("jobspy:"))
            if p["failed"] >= p["of"]:
                problems.append(f"❌ {name} failed this run (others OK)")
            elif p["soft"]:
                problems.append(f"⚠️ {name}: no results for {p['failed']} of {p['of']} filters")
            else:
                problems.append(f"⚠️ {name}: errors in {p['failed']} of {p['of']} filters")
        errors = run.get("errors") or []
        problems += [f"🛑 {_e(e.get('message'))}" for e in (json.loads(errors) if isinstance(errors, str) else errors)
                     if e.get("source") == "run"]
        if problems:
            body += ["", "<b>🛠 Problems</b>", *problems]

    if not body:
        return ""
    return "\n".join([f"🔎 <b>{TRIGGERS.get(trigger, 'Run')}</b>{when}", *body, "", link(base, "Open JobHunter")])


def notify_run_finished(conn: sqlite3.Connection, run: dict, summary: str) -> str:
    text = run_message(conn, run, summary)
    return send(text, conn) if text else "nothing to send"


def log_error(log_file: str | None) -> str:
    """The last `Error: …` line a stage wrote to the run log (cli.py agent prints its setup errors
    that way, e.g. a provider without a model), so the failure message says what to fix."""
    if not log_file:
        return ""
    path = ROOT / log_file if not os.path.isabs(log_file) else log_file
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return ""
    errors = [ln[len("Error: "):].strip() for ln in lines if ln.startswith("Error: ")]
    return errors[-1][:300] if errors else ""


def notify_run_failed(conn: sqlite3.Connection | None, reason: str, log_file: str | None = None) -> str:
    if not enabled(conn, "notify_failures"):
        return "disabled"
    text = f"🛑 Run failed: {_e(reason)}" + (f" — see {_e(log_file)}" if log_file else "")
    cause = log_error(log_file)
    if cause:
        text += f"\n<b>Cause:</b> {_e(cause)}"
    return send(text, conn)


def notify_run_refused(conn: sqlite3.Connection, trigger: str, reason: str) -> str:
    """A run the user started from the UI ("Generate now", "Evaluate now") couldn't start.
    Scheduled runs refused by the time guard stay quiet."""
    if not enabled(conn, "notify_failures"):
        return "disabled"
    what = {"docs": "Generate now", "single": "Evaluate now", "manual": "Run now",
            "evaluate": "Score waiting jobs"}.get(trigger, trigger)
    return send(f"⏸ {what} couldn't start: {_e(reason)}", conn)
