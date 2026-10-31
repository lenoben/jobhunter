"""Feedback tickets (core §16d). The UI stores the tickets and writes their text; this module holds
the developer's address, the optional technical details and the mailbox draft. Never sends (R1)."""

from __future__ import annotations

import platform
import subprocess

from core import agent, mail_config, mail_drafts
from core.db import ROOT

DEV_EMAIL = "dev@lenoben.top"


def _commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                           text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "unknown"


def details() -> dict[str, str]:
    """What the optional "technical details" box adds. Nothing personal: no user or host name, no
    paths, no keys (R3/R4); the provider is its name only."""
    return {"os": f"{platform.system()} {platform.release()}".strip(),
            "llm_provider": agent.provider_name(), "commit": _commit()}


def info() -> dict:
    """Everything the feedback page needs from Python."""
    return {"to": DEV_EMAIL, "details": details(), "drafts_available": mail_config.configured("send")}


def save_draft(subject: str, body: str) -> dict:
    """Puts the ticket in the Drafts folder of the user's SEND mailbox. The recipient is fixed here,
    so this can't draft to anyone else; the user sends it themselves."""
    if not mail_config.configured("send"):
        raise RuntimeError("No drafts mailbox is set up (run: uv run python cli.py setup)")
    return mail_drafts.create_draft(DEV_EMAIL, subject, body)
