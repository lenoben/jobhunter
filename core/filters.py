"""Search filters: load from DB and seed the starter set (CLAUDE.md §15) or the user's own."""

from __future__ import annotations

import sqlite3

from core.models import SearchFilter

DEFAULT_EXCLUDES = ["Freelance", "Freiberuflich", "Selbstständig", "Senior Principal"]

# IT starter set (the project owner's search); cli.py setup lets a new user enter their own instead.
DEFAULT_FILTERS: list[tuple[str, list[str]]] = [
    ("Software / Backend", ["Softwareentwickler", "Software Engineer", "Backend Developer",
                            "Full Stack Developer", "Python Developer", "Go Developer"]),
    ("AI / LLM / Data", ["Machine Learning Engineer", "AI Engineer", "LLM Engineer",
                         "Data Scientist", "Data Engineer", "NLP"]),
    ("Web / App", ["Web Developer", "Frontend Developer", "Mobile Developer",
                   "Flutter Developer", "App-Entwickler"]),
    ("DevOps / Cloud", ["DevOps Engineer", "Cloud Engineer", "Platform Engineer",
                        "Site Reliability Engineer"]),
    ("Computer Engineering", ["Embedded Software Engineer", "Firmware Entwickler", "Computer Engineer"]),
    ("Fintech / Health-tech", ["Fintech", "Bankensoftware", "Medizininformatik", "Health IT",
                               "Medizintechnik Software"]),
]


def load_filters(conn: sqlite3.Connection, active_only: bool = False) -> list[SearchFilter]:
    sql = "SELECT * FROM search_filters"
    if active_only:
        sql += " WHERE active = 1"
    return [SearchFilter.from_row(r) for r in conn.execute(sql + " ORDER BY id")]


def insert_filter(conn: sqlite3.Connection, f: SearchFilter) -> int:
    cols = f.to_db()
    placeholders = ", ".join(f":{k}" for k in cols)
    cur = conn.execute(
        f"INSERT INTO search_filters ({', '.join(cols)}) VALUES ({placeholders})", cols
    )
    return cur.lastrowid


def seed_default_filters(conn: sqlite3.Connection,
                         groups: list[tuple[str, list[str]]] | None = None) -> list[str]:
    """Insert filters that don't exist yet (matched by name): `groups` (the user's own, from
    cli.py setup) or the IT starter set DEFAULT_FILTERS. Returns the names inserted."""
    existing = {r["name"] for r in conn.execute("SELECT name FROM search_filters")}
    inserted = []
    for name, keywords in DEFAULT_FILTERS if groups is None else groups:
        if name in existing:
            continue
        insert_filter(conn, SearchFilter(
            name=name,
            keywords=keywords,
            exclude_keywords=list(DEFAULT_EXCLUDES),
            location=None,
            work_modes=["remote", "hybrid", "onsite"],
            employment_types=["full_time"],
            exclude_freelance=True,
        ))
        inserted.append(name)
    conn.commit()
    return inserted
