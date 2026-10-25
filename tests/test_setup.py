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
    assert settings == {"search_countries": '["uk", "usa"]'}
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
