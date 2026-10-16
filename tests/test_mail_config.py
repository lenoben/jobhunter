import pytest

from core import mail_config, mail_drafts

KEYS = [f"{p}_{k}" for p in ("SEND", "ALERTS") for k in ("MAIL_ADDRESS", "MAIL_APP_PASSWORD", "IMAP_HOST", "IMAP_PORT")]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr(mail_config, "_load_dotenv", lambda: None)  # never read the real .env
    for k in KEYS + ["MAIL_ADDRESS"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SEND_MAIL_ADDRESS", "me@myyahoo.com")
    monkeypatch.setenv("SEND_MAIL_APP_PASSWORD", "abcd efgh ijkl mnop")


def test_send_defaults_to_yahoo():
    cfg = mail_config.load_send_config()
    assert (cfg.role, cfg.host, cfg.port, cfg.app_password) == ("send", "imap.mail.yahoo.com", 993, "abcdefghijklmnop")


def test_alerts_falls_back_to_send_but_stays_alerts_role():
    cfg = mail_config.load_alerts_config()
    assert cfg.role == "alerts" and cfg.source == "SEND" and cfg.address == "me@myyahoo.com"


def test_alerts_own_account(monkeypatch):
    monkeypatch.setenv("ALERTS_MAIL_ADDRESS", "alerts@gmail.com")
    monkeypatch.setenv("ALERTS_MAIL_APP_PASSWORD", "x")
    monkeypatch.setenv("ALERTS_IMAP_HOST", "imap.gmail.com")
    cfg = mail_config.load_alerts_config()
    assert (cfg.role, cfg.source, cfg.address, cfg.host) == ("alerts", "ALERTS", "alerts@gmail.com", "imap.gmail.com")


def test_alerts_account_needs_a_host(monkeypatch):
    monkeypatch.setenv("ALERTS_MAIL_ADDRESS", "alerts@gmail.com")
    monkeypatch.setenv("ALERTS_MAIL_APP_PASSWORD", "x")
    with pytest.raises(RuntimeError, match="ALERTS_IMAP_HOST"):
        mail_config.load_alerts_config()


def test_alerts_config_can_never_create_drafts(monkeypatch):
    monkeypatch.setattr(mail_drafts, "connect", lambda cfg: pytest.fail("must not connect"))
    with pytest.raises(RuntimeError, match="only be created in the SEND account"):
        mail_drafts.create_draft("x@example.com", "s", "b", cfg=mail_config.load_alerts_config())


def test_missing_send_account_hints_at_rename(monkeypatch):
    monkeypatch.delenv("SEND_MAIL_ADDRESS")
    monkeypatch.setenv("MAIL_ADDRESS", "old@myyahoo.com")
    with pytest.raises(RuntimeError, match="renamed to SEND_MAIL_ADDRESS"):
        mail_config.load_send_config()


def test_repr_hides_password():
    assert "abcd" not in repr(mail_config.load_send_config())
