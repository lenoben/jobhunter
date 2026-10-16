"""SQLite connection, pragmas and the numbered-migration runner. Python owns the schema."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def db_path() -> Path:
    override = os.environ.get("JOBHUNTER_DB")
    return Path(override) if override else ROOT / "data" / "jobhunter.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply every migration in core/migrations/ not yet recorded. Returns the newly applied names."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version    TEXT PRIMARY KEY,
               applied_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    newly_applied = []
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if sql_file.name in applied:
            continue
        script = sql_file.read_text(encoding="utf-8")
        # executescript commits first and cannot run inside our transaction, so record the version
        # in the same script to keep "schema changed" and "migration recorded" atomic.
        conn.executescript(
            "BEGIN;\n"
            + _strip_pragmas(script)
            + f"\nINSERT INTO schema_migrations (version) VALUES ('{sql_file.name}');\nCOMMIT;"
        )
        newly_applied.append(sql_file.name)
    # Connection-level pragmas are set in connect(); re-assert after executescript.
    conn.execute("PRAGMA foreign_keys = ON")
    return newly_applied


def _strip_pragmas(script: str) -> str:
    # journal_mode cannot change inside a transaction; connect() already sets both pragmas.
    return "\n".join(
        line for line in script.splitlines() if not line.strip().upper().startswith("PRAGMA ")
    )


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def init_db(path: Path | None = None) -> tuple[Path, list[str]]:
    path = path or db_path()
    with connect(path) as conn:
        applied = migrate(conn)
    conn.close()
    return path, applied
