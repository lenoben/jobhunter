"""The browser setup page (/setup, core §16g): the choices of `cli.py setup`, one step per call.

state() never returns a secret, only whether it is set; apply() takes new secrets in and writes
them to .env (R3). An empty secret field keeps the stored one.
"""

from __future__ import annotations

import json
import shutil
import sqlite3

from core import agent, countries, db, mail_config, mail_drafts, notify, setup
from core.filters import DEFAULT_FILTERS, load_filters, seed_default_filters

CLAUDE_MODELS = ("haiku", "sonnet", "opus")
Step = tuple[dict[str, str], dict[str, str], dict]  # .env updates, setting updates, what the page shows


def _mail_state(env: dict[str, str], prefix: str) -> dict:
    return {"address": env.get(f"{prefix}_MAIL_ADDRESS", ""), "host": env.get(f"{prefix}_IMAP_HOST", ""),
            "password_set": bool(env.get(f"{prefix}_MAIL_APP_PASSWORD"))}


def state() -> dict:
    """What the page shows. Creates .env, the profile file and the database if they are missing."""
    setup.ensure_files(setup.Wizard(say=lambda _text: None))
    db.init_db()
    env = setup.read_env()
    conn = db.connect()
    try:
        settings, filters = db.get_settings(conn), len(load_filters(conn))
    finally:
        conn.close()
    provider = env.get("LLM_PROVIDER") or "claude-code"
    claude = bool(shutil.which("claude"))
    key_set = bool(env.get("LLM_API_KEY"))
    if provider == "claude-code":
        llm_done = claude
    else:
        llm_done = (key_set or provider == "ollama") and all(settings.get(k) for k in ("llm_model_filter", "llm_model_writer"))
    telegram_done = bool(env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"))
    return {
        "llm": {"provider": provider, "suggested": setup.suggested_provider(env), "providers": setup.LLM_CHOICES,
                "base_url": env.get("LLM_BASE_URL", ""),
                "key_set": key_set, "claude_installed": claude, "claude_models": CLAUDE_MODELS,
                "key_urls": {name: url for name, (_base, url) in agent.PROVIDERS.items() if url},
                "model_filter": settings.get("model_filter") or "haiku",
                "model_writer": settings.get("model_writer") or "sonnet",
                "llm_model_filter": settings.get("llm_model_filter", ""),
                "llm_model_writer": settings.get("llm_model_writer", ""), "done": llm_done},
        "countries": {"keys": countries.from_setting(settings.get("search_countries")),
                      "common": [{"key": k, "label": countries.label(k)} for k in countries.COMMON],
                      "himalayas_set": bool(env.get("HIMALAYAS_API_KEY"))},
        "mail": {"send": _mail_state(env, "SEND"), "alerts": _mail_state(env, "ALERTS")},
        "telegram": {"token_set": bool(env.get("TELEGRAM_BOT_TOKEN")), "done": telegram_done},
        "permit": settings.get("work_permit_checks", "1") == "1",
        "filters": {"count": filters, "starter": [name for name, _ in DEFAULT_FILTERS]},
        "done": llm_done and telegram_done and filters > 0,
    }


def _text(p: dict, key: str) -> str:
    return str(p.get(key) or "").strip()


def _llm(p: dict, env: dict[str, str], settings: dict[str, str], conn: sqlite3.Connection) -> Step:
    provider = _text(p, "provider")
    if provider not in setup.LLM_CHOICES:
        raise ValueError("Pick an AI provider.")
    if provider == "claude-code":
        models = {k: _text(p, k) or settings.get(k) or d for k, d in (("model_filter", "haiku"), ("model_writer", "sonnet"))}
        if not set(models.values()) <= set(CLAUDE_MODELS):
            raise ValueError("Pick the models from the list.")
        warning = "" if shutil.which("claude") else ("Claude Code is not installed on this PC. Install it from "
                                                     "claude.com/claude-code and run “claude” once to log in.")
        return {"LLM_PROVIDER": provider}, models, {"warning": warning}

    base = _text(p, "base_url") if provider == "custom" else ""
    if provider == "custom" and not base:
        raise ValueError("Enter the API base URL (it ends in /v1).")
    changed = provider != env.get("LLM_PROVIDER")
    key = _text(p, "api_key") or ("" if changed else env.get("LLM_API_KEY", ""))
    if not key and provider != "ollama":
        raise ValueError("Enter the API key.")
    out_env = {"LLM_PROVIDER": provider, "LLM_BASE_URL": base, "LLM_API_KEY": key}
    result: dict = {}
    try:
        result["models"] = agent.list_models(agent.LLMConfig(provider, (base or agent.PROVIDERS[provider][0]).rstrip("/"), key))
    except Exception as e:  # same as the wizard: save anyway, the user types the model ids
        result["models"] = []
        result["warning"] = (f"Couldn't list the models ({agent.describe_error(e)}). Runs will fail the same way "
                             "until that is fixed; check the key, or type the model ids yourself.")
    # Models of another provider don't exist here: forget them until the user picks new ones.
    chosen = {k: _text(p, k) or ("" if changed else settings.get(k, "")) for k in ("llm_model_filter", "llm_model_writer")}
    result["need_models"] = not all(chosen.values())
    result["suggested"] = agent.suggest_models(result["models"])
    if result["models"]:  # kept for the model lists in /settings (changeable later, user request 2026-11-20)
        chosen["llm_models"] = json.dumps(result["models"])
    return out_env, chosen, result


def _countries(p: dict, env: dict[str, str], settings: dict[str, str], conn: sqlite3.Connection) -> Step:
    keys, unknown = countries.parse(_text(p, "countries"))
    if unknown:
        raise ValueError(f"Unknown: {', '.join(unknown)}. Use country names, “remote” or “worldwide”.")
    if not keys:
        raise ValueError("Name at least one country.")
    return ({"HIMALAYAS_API_KEY": _text(p, "himalayas_key") or env.get("HIMALAYAS_API_KEY", "")},
            setup.country_settings(keys, settings), {})


def _mail_account(p: dict, env: dict[str, str], prefix: str, label: str) -> dict[str, str]:
    """One mailbox: empty address = not used. Logs in once, so a wrong app password shows now."""
    low = prefix.lower()
    address = _text(p, f"{low}_address")
    if not address:
        return {f"{prefix}_MAIL_ADDRESS": "", f"{prefix}_MAIL_APP_PASSWORD": ""}
    guessed = mail_config.guess_host(address)
    host = guessed or _text(p, f"{low}_host")
    if not host:
        raise ValueError(f"{label}: enter the IMAP host for {address} (your mail provider's help lists it).")
    same = address == env.get(f"{prefix}_MAIL_ADDRESS")
    password = _text(p, f"{low}_password").replace(" ", "") or (env.get(f"{prefix}_MAIL_APP_PASSWORD", "") if same else "")
    if not password:
        raise ValueError(f"{label}: enter the app password (not your normal password).")
    try:
        mail_drafts.connect(mail_config.MailConfig(address, password, host)).logout()
    except (RuntimeError, OSError) as e:
        raise ValueError(f"{label}: {e}") from None
    return {f"{prefix}_MAIL_ADDRESS": address, f"{prefix}_MAIL_APP_PASSWORD": password,
            f"{prefix}_MAIL_PROVIDER": "", f"{prefix}_IMAP_HOST": "" if guessed else host}


def _mail(p: dict, env: dict[str, str], settings: dict[str, str], conn: sqlite3.Connection) -> Step:
    return (_mail_account(p, env, "SEND", "Drafts mailbox") | _mail_account(p, env, "ALERTS", "Job-alert mailbox"),
            {}, {})


def _telegram(p: dict, env: dict[str, str], settings: dict[str, str], conn: sqlite3.Connection) -> Step:
    """Required. Two clicks: the token (checked with Telegram), then, after the user wrote to the
    bot, the chat is found and a test message sent. The token is saved after the first click."""
    new_token = _text(p, "token")
    token = new_token or env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("Paste the bot token from @BotFather.")
    name = notify.bot_username(token)  # RuntimeError: Telegram didn't accept the token
    chats = {str(c["id"]): c for c in notify.get_chat_ids(token)}
    # The saved chat stays unless the token is new: someone else may have written to the bot since.
    chat = (_text(p, "chat") or ("" if new_token else env.get("TELEGRAM_CHAT_ID", ""))
            or (next(iter(chats)) if len(chats) == 1 else ""))
    out_env = {"TELEGRAM_BOT_TOKEN": token}
    if not chat:
        options = [{"id": i, "label": f"{c['name']} ({c['type']})"} for i, c in chats.items()]
        return out_env, {}, {"pending": True, "bot": name, "chats": options}
    notify.send_with(token, chat, "✅ JobHunter is connected. Run summaries will arrive here.")
    return out_env | {"TELEGRAM_CHAT_ID": chat}, {"telegram_enabled": "1"}, {"bot": name}


def _permit(p: dict, env: dict[str, str], settings: dict[str, str], conn: sqlite3.Connection) -> Step:
    return {}, {"work_permit_checks": "1" if _text(p, "need") == "yes" else "0"}, {}


def _filters(p: dict, env: dict[str, str], settings: dict[str, str], conn: sqlite3.Connection) -> Step:
    if load_filters(conn):
        raise ValueError("You already have search filters; edit them on the Filters page.")
    if _text(p, "starter") == "yes":
        seed_default_filters(conn)
        return {}, {}, {}
    groups = setup.parse_filter_lines(_text(p, "lines").splitlines())
    if not groups:
        raise ValueError("Write at least one line like  Nursing: Registered Nurse, Pflegefachkraft")
    seed_default_filters(conn, groups)
    return {}, {}, {}


STEPS = {"llm": _llm, "countries": _countries, "mail": _mail, "telegram": _telegram, "permit": _permit,
         "filters": _filters}


def apply(p: dict) -> dict:
    """Save one step of the page. Raises ValueError / RuntimeError with a message for the user."""
    step = STEPS.get(str(p.get("step")))
    if not step:
        raise ValueError("unknown setup step")
    setup.ensure_files(setup.Wizard(say=lambda _text: None))
    db.init_db()
    conn = db.connect()
    try:
        env_updates, setting_updates, result = step(p, setup.read_env(), db.get_settings(conn), conn)
        setup.save(conn, env_updates, setting_updates)
    finally:
        conn.close()
    return {"ok": True, **result}
