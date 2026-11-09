"""cli.py setup (core/setup.py): .env editing, filter parsing and the wizard with scripted answers."""

import pytest

from core import db, setup
from core.filters import load_filters


def test_write_env_keeps_comments_and_order(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nA=1\n# B=commented\nB=\nC=3\n", encoding="utf-8")
    setup.write_env({"B": "two", "D": "4"}, env)
    assert env.read_text(encoding="utf-8") == "# comment\nA=1\n# B=commented\nB=two\nC=3\nD=4\n"
    assert setup.read_env(env) == {"A": "1", "B": "two", "C": "3", "D": "4"}


def test_parse_filter_lines():
    assert setup.parse_filter_lines(["Pflege: Pflegefachkraft, Krankenpfleger", "Erzieher", "  ", ":x"]) == [
        ("Pflege", ["Pflegefachkraft", "Krankenpfleger"]), ("Erzieher", ["Erzieher"])]


SENT: list[tuple[str, str]] = []  # Telegram test messages (token, chat) of the current test


class Script:
    def __init__(self, answers, secrets=()):
        self.answers, self.secrets, self.out = list(answers), list(secrets), []

    def wizard(self):
        return setup.Wizard(ask=lambda q: self.answers.pop(0), secret=lambda q: self.secrets.pop(0),
                            say=self.out.append)


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / ".env.example").write_text("LLM_PROVIDER=claude-code\nLLM_API_KEY=\nSEND_MAIL_ADDRESS=\n",
                                           encoding="utf-8")
    (tmp_path / "profile.example.yaml").write_text("personal: {}\n", encoding="utf-8")
    monkeypatch.setattr(setup, "ENV", tmp_path / ".env")
    monkeypatch.setattr(setup, "ENV_EXAMPLE", tmp_path / ".env.example")
    monkeypatch.setattr(setup, "PROFILE", tmp_path / "profile" / "profile.yaml")
    monkeypatch.setattr(setup, "PROFILE_EXAMPLE", tmp_path / "profile.example.yaml")
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "jobhunter.db"))
    monkeypatch.setattr(setup.agent, "list_models", lambda cfg: ["big-model", "small-model"])
    sent = SENT
    sent.clear()
    monkeypatch.setattr(setup.notify, "bot_username", lambda token: "jh_bot")
    monkeypatch.setattr(setup.notify, "get_chat_ids", lambda token: [{"id": 42, "type": "private", "name": "me"}])
    monkeypatch.setattr(setup.notify, "send_with", lambda token, chat, text: sent.append((token, chat)))
    return tmp_path


def _settings():
    conn = db.connect()
    try:
        return db.get_settings(conn), load_filters(conn)
    finally:
        conn.close()


def test_groq_gmail_only_eu_citizen_own_filters(home):
    s = Script(answers=["groq", "2", "1",                     # provider, filter model, writer model
                        "usa, 11",                            # USA + Remote (menu number)
                        "y", "me@gmail.com",                  # drafts mailbox (host guessed)
                        "1",                                  # alerts from the drafts mailbox
                        "",                                   # Enter after messaging the bot
                        "n",                                  # no work permit needed
                        "n", "Pflege: Pflegefachkraft, Krankenpfleger", ""],
               secrets=["gsk_test", "", "app-pw", "123:tok"])
    assert setup.run(s.wizard()) == 0
    env = setup.read_env(home / ".env")
    assert env["LLM_PROVIDER"] == "groq" and env["LLM_API_KEY"] == "gsk_test"
    assert env["SEND_MAIL_ADDRESS"] == "me@gmail.com" and env["SEND_MAIL_APP_PASSWORD"] == "app-pw"
    assert env["ALERTS_MAIL_ADDRESS"] == ""
    assert (env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_CHAT_ID"]) == ("123:tok", "42")
    assert SENT == [("123:tok", "42")]                   # the test message went out
    settings, filters = _settings()
    assert settings["search_countries"] == '["usa", "remote"]' 
    assert (settings["llm_model_filter"], settings["llm_model_writer"]) == ("small-model", "big-model")
    assert settings["work_permit_checks"] == "0" and settings["telegram_enabled"] == "1"
    assert [(f.name, f.keywords) for f in filters] == [("Pflege", ["Pflegefachkraft", "Krankenpfleger"])]
    assert (home / "profile" / "profile.yaml").exists()
    assert not any("gsk_test" in line or "app-pw" in line or "123:tok" in line for line in s.out)


def test_claude_code_yahoo_drafts_gmail_alerts(home):
    s = Script(answers=["1", "", "",                          # claude-code, default models
                        "",                                   # countries: default Germany
                        "y", "me@yahoo.com",
                        "2", "alerts@gmail.com",              # alerts from another mailbox
                        "", "y", "y"],                        # Telegram, needs a permit, starter set
               secrets=["", "pw1", "pw2", "tok"])
    assert setup.run(s.wizard()) == 0
    env = setup.read_env(home / ".env")
    assert env["LLM_PROVIDER"] == "claude-code"
    assert env["ALERTS_MAIL_ADDRESS"] == "alerts@gmail.com" and env["ALERTS_MAIL_APP_PASSWORD"] == "pw2"
    settings, filters = _settings()
    assert (settings["model_filter"], settings["model_writer"]) == ("haiku", "sonnet")
    assert settings["work_permit_checks"] == "1" and len(filters) == 6
    assert settings["search_countries"] == '["germany"]' and filters[0].countries == []


def test_telegram_retries_until_it_works(home, monkeypatch):
    def username(token):
        if token != "good":
            raise RuntimeError("Unauthorized")
        return "jh_bot"
    replies = iter([[], [{"id": 7, "type": "private", "name": "me"}]])
    monkeypatch.setattr(setup.notify, "bot_username", username)
    monkeypatch.setattr(setup.notify, "get_chat_ids", lambda token: next(replies))
    s = Script(answers=["", ""], secrets=["", "bad", "good"])  # empty, wrong, right token; Enter twice
    env, settings = setup.ask_telegram(s.wizard(), {})
    assert env == {"TELEGRAM_BOT_TOKEN": "good", "TELEGRAM_CHAT_ID": "7"} and settings == {"telegram_enabled": "1"}
    assert any("required" in line for line in s.out) and any("No message yet" in line for line in s.out)


def test_telegram_keeps_a_working_bot(home):
    s = Script(answers=["y"])
    env, settings = setup.ask_telegram(s.wizard(), {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"})
    assert env == {} and settings == {"telegram_enabled": "1"} and SENT == [("t", "1")]


def test_countries_rejects_unknown_names(home):
    s = Script(answers=["Atlantis", "uk, United States"], secrets=[""])
    env, settings = setup.ask_countries(s.wizard(), {}, {})
    assert settings == {"search_countries": '["uk", "usa"]', "cv_ats_friendly": "1"}
    again = Script(answers=["uk, usa"], secrets=[""])  # unchanged countries keep the user's choice
    assert "cv_ats_friendly" not in setup.ask_countries(again.wizard(), {}, settings)[1]
    assert any("Unknown: Atlantis" in line for line in s.out)


def test_model_list_failure_is_explained_and_a_model_is_required(home, monkeypatch):
    """Setup used to accept an empty model when /models failed, so every run then stopped (2026-10-26)."""
    import httpx

    def blocked(cfg):
        r = httpx.Response(403, json={"error": {"message": "Access denied."}},
                           request=httpx.Request("GET", "https://api.example/v1/models"))
        raise httpx.HTTPStatusError("403", request=r.request, response=r)

    monkeypatch.setattr(setup.agent, "list_models", blocked)
    s = Script(answers=["groq", "", "small-model", "big-model"], secrets=["gsk_test"])
    _, settings = setup.ask_llm(s.wizard(), {}, {})
    assert settings == {"llm_model_filter": "small-model", "llm_model_writer": "big-model"}
    out = "\n".join(s.out)
    assert "HTTP 403: Access denied." in out and "VPN" in out and "A model id is required" in out


# --- the browser setup page (core/onboarding.py, core §16g) -------------------------------------

def test_onboarding_state_never_holds_a_secret(home):
    import json

    from core import onboarding
    onboarding.apply({"step": "llm", "provider": "groq", "api_key": "gsk_secret",
                      "llm_model_filter": "small-model", "llm_model_writer": "big-model"})
    onboarding.apply({"step": "telegram", "token": "123:tg_secret"})
    state = onboarding.state()
    assert state["llm"]["key_set"] and state["llm"]["done"] and state["telegram"]["done"]
    text = json.dumps(state)
    assert "gsk_secret" not in text and "tg_secret" not in text
    env = setup.read_env()
    assert env["LLM_API_KEY"] == "gsk_secret" and env["TELEGRAM_CHAT_ID"] == "42" and SENT == [("123:tg_secret", "42")]


def test_onboarding_empty_secret_keeps_the_stored_one_but_not_across_providers(home):
    from core import onboarding
    first = onboarding.apply({"step": "llm", "provider": "groq", "api_key": "gsk_1"})
    assert first["models"] == ["big-model", "small-model"] and first["need_models"]
    onboarding.apply({"step": "llm", "provider": "groq", "llm_model_filter": "small-model", "llm_model_writer": "big-model"})
    assert setup.read_env()["LLM_API_KEY"] == "gsk_1" and _settings()[0]["llm_model_writer"] == "big-model"
    with pytest.raises(ValueError, match="API key"):
        onboarding.apply({"step": "llm", "provider": "openai"})


def test_onboarding_telegram_waits_for_a_message(home, monkeypatch):
    from core import onboarding
    monkeypatch.setattr(setup.notify, "get_chat_ids", lambda token: [])
    r = onboarding.apply({"step": "telegram", "token": "123:abc"})
    assert r["pending"] and r["bot"] == "jh_bot" and not SENT
    assert setup.read_env()["TELEGRAM_BOT_TOKEN"] == "123:abc" and not onboarding.state()["telegram"]["done"]


def test_onboarding_countries_mail_permit_filters(home, monkeypatch):
    from core import onboarding
    with pytest.raises(ValueError, match="Atlantis"):
        onboarding.apply({"step": "countries", "countries": "Atlantis"})
    onboarding.apply({"step": "countries", "countries": "uk, United States"})
    logins = []
    monkeypatch.setattr(onboarding.mail_drafts, "connect",
                        lambda cfg: logins.append((cfg.address, cfg.host)) or type("C", (), {"logout": lambda self: None})())
    with pytest.raises(ValueError, match="IMAP host"):
        onboarding.apply({"step": "mail", "send_address": "me@example.org", "send_password": "pw"})
    onboarding.apply({"step": "mail", "send_address": "me@gmail.com", "send_password": "ab cd"})
    onboarding.apply({"step": "permit", "need": "no"})
    onboarding.apply({"step": "filters", "lines": "Nursing: Registered Nurse"})
    settings, filters = _settings()
    env = setup.read_env()
    assert settings["search_countries"] == '["uk", "usa"]' and settings["cv_ats_friendly"] == "1"
    assert settings["work_permit_checks"] == "0" and [f.name for f in filters] == ["Nursing"]
    assert logins == [("me@gmail.com", "imap.gmail.com")] and env["SEND_MAIL_APP_PASSWORD"] == "abcd"
    assert env["ALERTS_MAIL_ADDRESS"] == ""


def test_a_fresh_pc_without_claude_code_is_offered_gemini(monkeypatch):
    """User decision 2026-11-16: most people start with Gemini's free tier."""
    monkeypatch.setattr(setup.shutil, "which", lambda tool: None)
    assert setup.suggested_provider({"LLM_PROVIDER": "claude-code"}) == "gemini"
    assert setup.suggested_provider({"LLM_PROVIDER": "claude-code", "LLM_API_KEY": "k"}) == "claude-code"
    assert setup.suggested_provider({"LLM_PROVIDER": "groq"}) == "groq"
    monkeypatch.setattr(setup.shutil, "which", lambda tool: "C:/claude.exe")
    assert setup.suggested_provider({}) == "claude-code"
