"""The two mail accounts, read from .env only (R3).

- SEND account (SEND_*): mail_drafts.py creates application drafts there. Never sends (R1).
- ALERTS account (ALERTS_*): read-only, for the email_alerts source (job-alert emails). If its
  address or app password is empty, the SEND account's credentials are used to read alerts.
  A config loaded for the alerts role can never be used to create drafts (mail_drafts checks
  `role`), even when it falls back to the SEND credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from core.db import ROOT

DEFAULT_HOST = "imap.mail.yahoo.com"
DEFAULT_PORT = 993


@dataclass
class MailConfig:
    address: str
    app_password: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    role: Literal["send", "alerts"] = "send"
    source: str = "SEND"          # which .env prefix the credentials came from

    def __repr__(self) -> str:  # keep the password out of logs and tracebacks
        return (f"MailConfig(role={self.role!r}, source={self.source!r}, address={self.address!r}, "
                f"host={self.host!r}, port={self.port})")


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _load_dotenv() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")


def _from_prefix(prefix: str, role: str, default_host: str | None) -> MailConfig | None:
    address = _env(f"{prefix}_MAIL_ADDRESS")
    password = _env(f"{prefix}_MAIL_APP_PASSWORD").replace(" ", "")
    if not address or not password:
        return None
    host = _env(f"{prefix}_IMAP_HOST") or default_host
    if not host:
        raise RuntimeError(f"{prefix}_IMAP_HOST must be set in .env")
    return MailConfig(address=address, app_password=password, host=host,
                      port=int(_env(f"{prefix}_IMAP_PORT") or DEFAULT_PORT), role=role, source=prefix)


def load_send_config() -> MailConfig:
    """The account application drafts are saved to."""
    _load_dotenv()
    cfg = _from_prefix("SEND", "send", DEFAULT_HOST)
    if cfg is None:
        hint = (" (MAIL_ADDRESS/MAIL_APP_PASSWORD were renamed to SEND_MAIL_ADDRESS/SEND_MAIL_APP_PASSWORD)"
                if _env("MAIL_ADDRESS") else "")
        raise RuntimeError("SEND_MAIL_ADDRESS and SEND_MAIL_APP_PASSWORD must be set in .env" + hint)
    return cfg


def load_alerts_config() -> MailConfig:
    """The read-only account job alerts are read from; falls back to the SEND credentials.
    The ALERTS account is not assumed to be Yahoo: ALERTS_IMAP_HOST is required when it is set."""
    _load_dotenv()
    cfg = _from_prefix("ALERTS", "alerts", None)
    if cfg is None:
        send = load_send_config()
        cfg = MailConfig(address=send.address, app_password=send.app_password, host=send.host,
                         port=send.port, role="alerts", source="SEND")
    return cfg


def load_config(account: Literal["send", "alerts"]) -> MailConfig:
    return load_send_config() if account == "send" else load_alerts_config()
