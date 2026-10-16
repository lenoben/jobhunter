"""Save application emails as IMAP drafts in the SEND account (Yahoo by default). Never sends (R1).

Config comes from .env only (R3): SEND_MAIL_ADDRESS, SEND_MAIL_APP_PASSWORD, SEND_IMAP_HOST,
SEND_IMAP_PORT (see core/mail_config.py). The ALERTS account is never used here.
"""

from __future__ import annotations

import imaplib
import mimetypes
import re
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from core.mail_config import MailConfig, load_send_config

# e.g. (\HasNoChildren \Drafts) "/" "Draft"
_LIST_RE = re.compile(r'\((?P<flags>[^)]*)\)\s+(?P<delim>"[^"]*"|NIL)\s+(?P<name>.+)')
FALLBACK_DRAFT_NAMES = ("Draft", "Drafts")


@dataclass
class Folder:
    name: str        # raw (modified UTF-7) mailbox name as the server returned it
    flags: list[str]


def load_config() -> MailConfig:
    return load_send_config()


def connect(cfg: MailConfig) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(cfg.host, cfg.port, timeout=30)
    try:
        conn.login(cfg.address, cfg.app_password)
    except imaplib.IMAP4.error as e:
        conn.shutdown()
        raise RuntimeError(f"IMAP login failed for {cfg.address} at {cfg.host} "
                           f"(check the app password): {e}") from None
    return conn


def parse_list_line(line: bytes | str) -> Folder | None:
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    m = _LIST_RE.match(line)
    if not m:
        return None
    name = m.group("name").strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return Folder(name=name, flags=m.group("flags").split())


def list_folders(conn: imaplib.IMAP4_SSL) -> list[Folder]:
    typ, data = conn.list()
    if typ != "OK":
        raise RuntimeError(f"IMAP LIST failed: {data}")
    return [f for line in data if line and (f := parse_list_line(line))]


def find_drafts_folder(folders: list[Folder]) -> tuple[str, str]:
    """Return (folder name, how it was found). Prefers the RFC 6154 \\Drafts special-use flag,
    falls back to a folder literally named Draft or Drafts."""
    for f in folders:
        if any(flag.lower() == "\\drafts" for flag in f.flags):
            return f.name, "\\Drafts flag"
    by_name = {f.name.lower(): f.name for f in folders}
    for candidate in FALLBACK_DRAFT_NAMES:
        if candidate.lower() in by_name:
            return by_name[candidate.lower()], "name fallback"
    raise RuntimeError("No Drafts folder: none has the \\Drafts flag and none is named "
                       + " or ".join(FALLBACK_DRAFT_NAMES))


def build_message(sender: str, to: str, subject: str, body: str,
                  attachments: list[Path] = ()) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(body)
    for path in attachments:
        path = Path(path)
        ctype, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    return msg


def create_draft(to: str, subject: str, body: str, attachments: list[Path] = (),
                 cfg: MailConfig | None = None) -> dict:
    """APPEND the message to the Drafts folder with the \\Draft flag, then confirm it is there.
    Returns {folder, found_by, message_id, confirmed}."""
    cfg = cfg or load_send_config()
    if cfg.role != "send":
        raise RuntimeError("drafts can only be created in the SEND account, never with the ALERTS config")
    msg = build_message(cfg.address, to, subject, body, attachments)
    conn = connect(cfg)
    try:
        folder, found_by = find_drafts_folder(list_folders(conn))
        typ, data = conn.append(_quote(folder), r"(\Draft)",
                                imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if typ != "OK":
            raise RuntimeError(f"IMAP APPEND to {folder} failed: {data}")
        confirmed = _draft_exists(conn, folder, msg["Message-ID"])
        return {"folder": folder, "found_by": found_by,
                "message_id": msg["Message-ID"], "confirmed": confirmed}
    finally:
        conn.logout()


def find_folder_by_flag(folders: list[Folder], flag: str, names: tuple[str, ...]) -> str | None:
    for f in folders:
        if any(x.lower() == flag.lower() for x in f.flags):
            return f.name
    by_name = {f.name.lower(): f.name for f in folders}
    return next((by_name[n.lower()] for n in names if n.lower() in by_name), None)


def inspect_message(message_id: str, cfg: MailConfig | None = None) -> dict:
    """Read-only check (EXAMINE + BODY.PEEK, no flags change): is the message in Drafts, is it in
    Sent, and which attachments does the stored copy have? Returns
    {in_drafts, in_sent, attachments: [filename, …], draft_flag}."""
    import email

    cfg = cfg or load_send_config()
    conn = connect(cfg)
    try:
        folders = list_folders(conn)
        drafts, _ = find_drafts_folder(folders)
        sent = find_folder_by_flag(folders, "\\Sent", ("Sent", "Sent Items", "Gesendet"))
        out = {"in_drafts": False, "in_sent": False, "attachments": [], "draft_flag": False}
        for key, folder in (("in_drafts", drafts), ("in_sent", sent)):
            if not folder or conn.select(_quote(folder), readonly=True)[0] != "OK":
                continue
            typ, data = conn.search(None, "HEADER", "Message-ID", f'"{message_id}"')
            nums = data[0].split() if typ == "OK" and data and data[0] else []
            out[key] = bool(nums)
            if key == "in_drafts" and nums:
                typ, parts = conn.fetch(nums[-1], "(FLAGS BODY.PEEK[])")
                raw = next(p[1] for p in parts if isinstance(p, tuple))
                flags = b" ".join(p[0] for p in parts if isinstance(p, tuple))
                out["draft_flag"] = b"\\Draft" in flags
                msg = email.message_from_bytes(raw)
                out["attachments"] = [p.get_filename() for p in msg.walk() if p.get_filename()]
        return out
    finally:
        conn.logout()


def _draft_exists(conn: imaplib.IMAP4_SSL, folder: str, message_id: str) -> bool:
    typ, _ = conn.select(_quote(folder), readonly=True)
    if typ != "OK":
        return False
    typ, data = conn.search(None, "HEADER", "Message-ID", f'"{message_id}"')
    return typ == "OK" and bool(data and data[0].split())


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'
