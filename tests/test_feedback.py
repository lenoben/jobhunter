"""Feedback tickets (user request 2026-11-07, core §16d): the mailbox draft and the technical details."""

import getpass
import json
import platform

import pytest

import cli
from core import db, feedback, mail_config, mail_drafts


def test_draft_goes_to_the_developer_only(monkeypatch):
    calls = []
    monkeypatch.setattr(mail_config, "configured", lambda account: True)
    monkeypatch.setattr(mail_drafts, "create_draft", lambda *a, **k: calls.append((a, k)) or {"folder": "Draft"})
    assert feedback.save_draft("[JobHunter Issue JH-ABCDE] Title", "Text") == {"folder": "Draft"}
    assert calls == [(("dev@lenoben.top", "[JobHunter Issue JH-ABCDE] Title", "Text"), {})]


def test_draft_without_a_mailbox_explains(monkeypatch):
    monkeypatch.setattr(mail_config, "configured", lambda account: False)
    with pytest.raises(RuntimeError, match="No drafts mailbox"):
        feedback.save_draft("s", "b")


def test_details_are_only_the_three_fields_and_nothing_personal(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    d = feedback.details()
    assert set(d) == {"os", "llm_provider", "commit"}
    assert d["llm_provider"] == "gemini"
    text = json.dumps(d)
    assert "secret-key" not in text
    assert getpass.getuser() not in text
    assert platform.node() not in text


def test_commit_is_unknown_without_git(monkeypatch):
    def no_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(feedback.subprocess, "run", no_git)
    assert feedback.details()["commit"] == "unknown"


def test_info_cli_applies_the_tickets_migration(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "f.db"))
    assert cli.main(["feedback-info", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["to"] == "dev@lenoben.top"
    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0
    conn.close()


def test_draft_cli_reports_an_error_as_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mail_config, "configured", lambda account: False)
    text = tmp_path / "t.txt"
    text.write_text("Grüße", encoding="utf-8")
    assert cli.main(["feedback-draft", "--subject", "s", "--text-file", str(text), "--json"]) == 1
    assert "No drafts mailbox" in json.loads(capsys.readouterr().out)["error"]
