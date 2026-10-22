"""`cli.py setup`: the guided first-time setup for a new user (user request 2026-10-25).

Asks for the user's own choices and writes them where they belong: secrets and accounts into
.env (R3), everything else into the settings table. Safe to run again: Enter keeps the current
value, and secrets already in .env are never printed (only "set" / "not set").
"""

from __future__ import annotations

import getpass
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Callable

from core import agent, countries, db, mail_config, notify
from core.db import ROOT
from core.filters import DEFAULT_FILTERS, load_filters, seed_default_filters

ENV = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
PROFILE = ROOT / "profile" / "profile.yaml"
PROFILE_EXAMPLE = ROOT / "profile.example.yaml"
LLM_CHOICES = ["claude-code", *agent.PROVIDERS, "custom"]


# --- .env -------------------------------------------------------------------------------------

def read_env(path: Path | None = None) -> dict[str, str]:
    path = path or ENV  # looked up at call time, so tests can point ENV elsewhere
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def write_env(updates: dict[str, str], path: Path | None = None) -> None:
    """Set KEY=value lines in place (comments and order kept); unknown keys are appended."""
    path = path or ENV
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    todo = dict(updates)
    for i, line in enumerate(lines):
        key = line.partition("=")[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in todo:
            lines[i] = f"{key}={todo.pop(key)}"
    lines += [f"{k}={v}" for k, v in todo.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- questions --------------------------------------------------------------------------------

class Wizard:
    def __init__(self, ask: Callable[[str], str] = input, secret: Callable[[str], str] = getpass.getpass,
                 say: Callable[[str], None] = print):
        self.ask_raw, self.secret_raw, self.say = ask, secret, say

    def ask(self, question: str, default: str = "") -> str:
        answer = self.ask_raw(f"{question}{f' [{default}]' if default else ''}: ").strip()
        return answer or default

    def yes(self, question: str, default: bool) -> bool:
        answer = self.ask(f"{question} (y/n)", "y" if default else "n").lower()
        return answer.startswith(("y", "j"))

    def choose(self, question: str, options: list[str], default: str) -> str:
        for i, o in enumerate(options, 1):
            self.say(f"  {i}. {o}")
        while True:
            answer = self.ask(question, default)
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return options[int(answer) - 1]
            if answer in options:
                return answer
            self.say(f"  Please pick 1–{len(options)}.")

    def secret(self, question: str, current: str) -> str:
        """Hidden input; Enter keeps the current secret."""
        answer = self.secret_raw(f"{question} ({'set — Enter keeps it' if current else 'not set'}): ").strip()
        return answer or current


# --- steps ------------------------------------------------------------------------------------

def check_requirements(w: Wizard) -> None:
    w.say("\n1. Requirements")
    for tool, why in (("claude", "Claude Code (only if you run with claude-code)"),
                      ("node", "Node LTS, for the web UI"), ("npm", "npm, for the web UI")):
        w.say(f"  {'✓' if shutil.which(tool) else '✗'} {tool}: {why}")
    try:
        import typst  # noqa: F401
        w.say("  ✓ typst (Python package, renders the PDFs)")
    except ImportError:
        w.say("  ✗ typst: run  uv sync")


def ensure_files(w: Wizard) -> None:
    w.say("\n2. Your files")
    if not ENV.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV)
        w.say("  created .env from .env.example")
    if not PROFILE.exists():
        PROFILE.parent.mkdir(exist_ok=True)
        shutil.copyfile(PROFILE_EXAMPLE, PROFILE)
        w.say("  created profile/profile.yaml from the example: fill it in with your real data")
        w.say("  (tip: ask Claude Code to fill it from your CV; it must never invent anything, R5)")
    else:
        w.say("  profile/profile.yaml exists")


def ask_llm(w: Wizard, env: dict[str, str], settings: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    w.say("\n3. AI that runs the search and writes the documents")
    w.say("  claude-code = Claude Code on your Claude subscription (best results, no API key).")
    w.say("  The others are OpenAI-compatible APIs with your own key. Open models invent facts more")
    w.say("  easily: check every CV and letter before you send it.")
    current = env.get("LLM_PROVIDER") or "claude-code"
    provider = w.choose("Provider", LLM_CHOICES, current if current in LLM_CHOICES else "claude-code")
    out_env, out_settings = {"LLM_PROVIDER": provider}, {}
    if provider == "claude-code":
        if not shutil.which("claude"):
            w.say("  ⚠ claude is not on PATH: install Claude Code and log in with your subscription")
        out_settings["model_filter"] = w.choose("Model for searching and scoring", ["haiku", "sonnet", "opus"],
                                                settings.get("model_filter") or "haiku")
        out_settings["model_writer"] = w.choose("Model for CVs and letters", ["sonnet", "opus", "haiku"],
                                                settings.get("model_writer") or "sonnet")
        return out_env, out_settings

    base_default = env.get("LLM_BASE_URL") or agent.PROVIDERS.get(provider, ("", ""))[0]
    base = w.ask("API base URL (OpenAI-compatible, ends in /v1)", base_default) if provider == "custom" else ""
    out_env["LLM_BASE_URL"] = base
    if provider != "ollama":
        keys_at = agent.PROVIDERS.get(provider, ("", ""))[1]
        if keys_at:
            w.say(f"  Create a key at {keys_at}")
        out_env["LLM_API_KEY"] = w.secret("API key", env.get("LLM_API_KEY", ""))
    cfg = agent.LLMConfig(provider, (base or base_default).rstrip("/"), out_env.get("LLM_API_KEY", ""))
    try:
        models = agent.list_models(cfg)
        w.say(f"  {len(models)} models available.")
    except Exception as e:
        w.say(f"  couldn't list the models ({type(e).__name__}); type the model ids yourself")
        models = []
    w.say("  Pick a fast, cheap model for searching/scoring and a strong one for writing.")
    for key, label in (("llm_model_filter", "Model for searching and scoring"),
                       ("llm_model_writer", "Model for CVs and letters")):
        current_model = settings.get(key, "")
        out_settings[key] = (w.choose(label, models, current_model if current_model in models else models[0])
                             if models else w.ask(label, current_model))
    return out_env, out_settings


def ask_countries(w: Wizard, env: dict[str, str], settings: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    w.say("\n4. Where do you want to work?")
    w.say("  Pick one or more, comma-separated: numbers from the list or any country name.")
    for i, key in enumerate(countries.COMMON, 1):
        w.say(f"  {i}. {countries.label(key)}")
    w.say("  Bundesagentur and Arbeitnow search Germany only; Indeed/LinkedIn/Glassdoor most countries;")
    w.say("  Himalayas and Jobicy remote jobs. Each filter can override this list later (/filters).")
    current = ", ".join(countries.from_setting(settings.get("search_countries")))
    while True:
        answer = w.ask("Countries", current)
        parts = [countries.COMMON[int(x) - 1] if x.strip().isdigit() and 1 <= int(x) <= len(countries.COMMON)
                 else x for x in answer.split(",")]
        keys, unknown = countries.parse(",".join(parts))
        if keys and not unknown:
            break
        w.say(f"  Unknown: {', '.join(unknown)}" if unknown else "  Name at least one.")
    w.say("  → " + ", ".join(map(countries.label, keys)))
    w.say("  Himalayas works without a key on a shared allowance; a free key (himalayas.app/api) is steadier.")
    key = w.secret("Himalayas API key (optional)", env.get("HIMALAYAS_API_KEY", ""))
    return {"HIMALAYAS_API_KEY": key}, {"search_countries": json.dumps(keys)}


def _ask_mail_account(w: Wizard, env: dict[str, str], prefix: str, label: str) -> dict[str, str]:
    address = w.ask(f"{label} address", env.get(f"{prefix}_MAIL_ADDRESS", ""))
    out = {f"{prefix}_MAIL_ADDRESS": address}
    guessed = mail_config.guess_host(address)
    if guessed and not env.get(f"{prefix}_IMAP_HOST"):
        w.say(f"  IMAP host: {guessed} (from the address)")
        out[f"{prefix}_MAIL_PROVIDER"] = ""
    else:
        names = [*mail_config.PROVIDERS, "other"]
        current = env.get(f"{prefix}_MAIL_PROVIDER") or "other"
        name = w.choose("Mail provider", names, current if current in names else "other")
        out[f"{prefix}_MAIL_PROVIDER"] = "" if name == "other" else name
        out[f"{prefix}_IMAP_HOST"] = (w.ask("IMAP host (SSL)", env.get(f"{prefix}_IMAP_HOST", ""))
                                      if name == "other" else "")
    w.say("  Use an app password (account security settings of your provider), never your normal one.")
    out[f"{prefix}_MAIL_APP_PASSWORD"] = w.secret("App password", env.get(f"{prefix}_MAIL_APP_PASSWORD", ""))
    return out


def ask_mail(w: Wizard, env: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    w.say("\n5. Email (optional; the two mailboxes can be different providers)")
    out_env: dict[str, str] = {}
    if w.yes("Save application emails as drafts in a mailbox? (nothing is ever sent)",
             bool(env.get("SEND_MAIL_ADDRESS"))):
        out_env |= _ask_mail_account(w, env, "SEND", "Drafts mailbox")
    else:
        out_env |= {"SEND_MAIL_ADDRESS": "", "SEND_MAIL_APP_PASSWORD": ""}
    w.say("  JobHunter can also read your LinkedIn/Instaffo job-alert emails (read-only).")
    if out_env.get("SEND_MAIL_ADDRESS"):
        options = ["the drafts mailbox", "another mailbox"]
        other = "another mailbox"
    else:
        options = ["no job alerts", "a mailbox"]
        other = "a mailbox"
    where = w.choose("Read job alerts from", options, other if env.get("ALERTS_MAIL_ADDRESS") else options[0])
    if where == other:
        out_env |= _ask_mail_account(w, env, "ALERTS", "Job-alert mailbox")
    else:
        out_env |= {"ALERTS_MAIL_ADDRESS": "", "ALERTS_MAIL_APP_PASSWORD": ""}
    return out_env, {}


def ask_telegram(w: Wizard, env: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Required (user decision 2026-10-25): run summaries, jobs that need you and failed runs
    arrive on Telegram. Finishes only when a test message went through."""
    w.say("\n6. Telegram (required: run summaries, jobs that need you, failed runs)")
    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")
    if token and chat:
        try:
            notify.send_with(token, chat, "✅ JobHunter setup: Telegram still works.")
            if w.yes("A test message was sent. Keep this bot and chat?", True):
                return {}, {"telegram_enabled": "1"}
        except RuntimeError as e:
            w.say(f"  The saved bot doesn't work any more ({e}); let's set it up again.")
    w.say("  1. In Telegram, open @BotFather and send /newbot.")
    w.say("  2. Choose a name and a username ending in 'bot'.")
    w.say("  3. Copy the token BotFather sends (looks like 123456:ABC…).")
    while True:
        token = w.secret("Bot token", token)
        if not token:
            w.say("  Telegram is required; paste the token from @BotFather.")
            continue
        try:
            name = notify.bot_username(token)
            break
        except RuntimeError as e:
            w.say(f"  Telegram didn't accept that token ({e}). Copy it again from @BotFather.")
            token = ""
    w.say(f"  4. Open https://t.me/{name} in Telegram, press Start or send any message.")
    while True:
        w.ask_raw("  Press Enter once you have sent the message ")
        try:
            chats = notify.get_chat_ids(token)
        except RuntimeError as e:
            w.say(f"  Couldn't ask Telegram ({e}); try again.")
            continue
        if not chats:
            w.say(f"  No message yet. Send one to @{name}, then press Enter.")
            continue
        if len(chats) == 1:
            chat = str(chats[0]["id"])
        else:
            labels = [f"{c['name']} ({c['type']}, {c['id']})" for c in chats]
            chat = str(chats[labels.index(w.choose("Which chat?", labels, labels[0]))]["id"])
        try:
            notify.send_with(token, chat, "✅ JobHunter is connected. Run summaries will arrive here.")
        except RuntimeError as e:
            w.say(f"  The test message failed ({e}); send the bot another message and press Enter.")
            continue
        w.say("  ✓ Test message sent. Check Telegram.")
        return {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat}, {"telegram_enabled": "1"}


def ask_work_permit(w: Wizard, settings: dict[str, str]) -> dict[str, str]:
    w.say("\n7. Work permit")
    w.say("  If you need a work permit or visa sponsorship where you apply, jobs that rule it out")
    w.say("  ('no visa sponsorship', 'US citizens only', 'unbefristete Arbeitserlaubnis') are flagged for")
    w.say("  you to decide. With Germany as a target, jobs below the EU Blue Card salary are flagged too.")
    need = w.yes("Do you need a work permit?", settings.get("work_permit_checks", "1") == "1")
    return {"work_permit_checks": "1" if need else "0"}


def parse_filter_lines(lines: list[str]) -> list[tuple[str, list[str]]]:
    """'Name: keyword, keyword' per line → filter groups; a line without ':' is its own name."""
    groups = []
    for line in lines:
        name, _, kws = line.partition(":")
        keywords = [k.strip() for k in (kws or name).split(",") if k.strip()]
        if name.strip() and keywords:
            groups.append((name.strip(), keywords))
    return groups


def ask_filters(w: Wizard, conn: sqlite3.Connection) -> None:
    w.say("\n8. What jobs to search for")
    existing = load_filters(conn)
    if existing:
        w.say(f"  You already have {len(existing)} search filter(s); edit them in the UI (/filters).")
        return
    w.say("  The IT starter set: " + "; ".join(name for name, _ in DEFAULT_FILTERS))
    if w.yes("Use the IT starter set?", True):
        seed_default_filters(conn)
        return
    w.say("  One filter per line as  Name: job title, job title  (titles in every language of your")
    w.say("  target countries help). Empty line = done. Example:  Nursing: Registered Nurse, Pflegefachkraft")
    lines = []
    while line := w.ask_raw("  > ").strip():
        lines.append(line)
    groups = parse_filter_lines(lines)
    seed_default_filters(conn, groups)
    w.say(f"  {len(groups)} filter(s) created.")


def run(w: Wizard | None = None) -> int:
    w = w or Wizard()
    w.say("JobHunter setup. Enter keeps the value in [brackets]; Ctrl+C stops without saving this step.")
    check_requirements(w)
    ensure_files(w)
    db.init_db()
    conn = db.connect()
    try:
        env, settings = read_env(), db.get_settings(conn)
        for step in (lambda: ask_llm(w, env, settings), lambda: ask_countries(w, env, settings),
                     lambda: ask_mail(w, env),
                     lambda: ask_telegram(w, env), lambda: ({}, ask_work_permit(w, settings))):
            env_updates, setting_updates = step()
            if env_updates:
                write_env(env_updates)
                env |= env_updates
            for k, v in setting_updates.items():
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, v))
            conn.commit()
        ask_filters(w, conn)
    finally:
        conn.close()
    w.say("\nDone. Next:")
    w.say("  • fill in profile/profile.yaml, then check it:  uv run python cli.py check-profile")
    if env.get("SEND_MAIL_ADDRESS") or env.get("ALERTS_MAIL_ADDRESS"):
        w.say("  • test the mailbox:  uv run python cli.py mail-test   (--account alerts for alerts)")
    w.say("  • web UI:  cd ui; npm install; npm run dev   → http://localhost:5173")
    w.say("  • twice-daily runs: Windows  .\\setup-task.ps1   ·  macOS/Linux  see README (run.sh + cron)")
    return 0
