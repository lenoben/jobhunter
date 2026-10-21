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

# Providers whose IMAP works with an app password. <PREFIX>_MAIL_PROVIDER picks one; without it the
# provider is guessed from the address' domain. <PREFIX>_IMAP_HOST always wins (any other provider).
# Outlook.com/Hotmail is missing on purpose: Microsoft no longer accepts app passwords over IMAP.
PROVIDERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "yahoo": ("imap.mail.yahoo.com", ("yahoo.com", "yahoo.de", "myyahoo.com", "ymail.com", "rocketmail.com")),
    "gmail": ("imap.gmail.com", ("gmail.com", "googlemail.com")),
    "gmx": ("imap.gmx.net", ("gmx.de", "gmx.net", "gmx.at", "gmx.ch")),
    "webde": ("imap.web.de", ("web.de",)),
    "t-online": ("secureimap.t-online.de", ("t-online.de",)),
    "icloud": ("imap.mail.me.com", ("icloud.com", "me.com", "mac.com")),
}


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
    host = _env(f"{prefix}_IMAP_HOST") or provider_host(prefix, address) or default_host
    if not host:
        raise RuntimeError(f"{prefix}_IMAP_HOST (or {prefix}_MAIL_PROVIDER) must be set in .env")
    return MailConfig(address=address, app_password=password, host=host,
                      port=int(_env(f"{prefix}_IMAP_PORT") or DEFAULT_PORT), role=role, source=prefix)


def provider_host(prefix: str, address: str) -> str | None:
    """IMAP host from <prefix>_MAIL_PROVIDER, else from the address' domain; None if unknown."""
    name = _env(f"{prefix}_MAIL_PROVIDER").lower().replace(".", "")
    if name:
        if name not in PROVIDERS:
            raise RuntimeError(f"{prefix}_MAIL_PROVIDER={name!r} is unknown; use one of "
                               f"{', '.join(PROVIDERS)} or set {prefix}_IMAP_HOST")
        return PROVIDERS[name][0]
    return guess_host(address)


def guess_host(address: str) -> str | None:
    """IMAP host of a known provider from the address' domain, else None."""
    domain = address.rpartition("@")[2].lower()
    return next((host for host, domains in PROVIDERS.values() if domain in domains), None)


def configured(account: Literal["send", "alerts"]) -> bool:
    """Is that mail account set up in .env? Mail is optional: without SEND no drafts are saved,
    without ALERTS (and SEND) the email_alerts source is skipped."""
    _load_dotenv()
    has = lambda prefix: bool(_env(f"{prefix}_MAIL_ADDRESS") and _env(f"{prefix}_MAIL_APP_PASSWORD"))
    return has("SEND") if account == "send" else has("ALERTS") or has("SEND")


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
    The ALERTS account is not assumed to be Yahoo: its host comes from ALERTS_IMAP_HOST,
    ALERTS_MAIL_PROVIDER or a known address domain, else it is an error."""
    _load_dotenv()
    cfg = _from_prefix("ALERTS", "alerts", None)
    if cfg is None:
        send = load_send_config()
        cfg = MailConfig(address=send.address, app_password=send.app_password, host=send.host,
                         port=send.port, role="alerts", source="SEND")
    return cfg


def load_config(account: Literal["send", "alerts"]) -> MailConfig:
    return load_send_config() if account == "send" else load_alerts_config()
