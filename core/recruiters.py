"""Recruiting agencies (user request 2026-10-28, core §16c).

A job whose company is a recruiter / staffing agency, or whose posting is written for a client,
never gets documents automatically: only when the user requests them. Two ways to find them:
- the user's list (`recruiters` table, /recruiters page): checked for every job when it is
  inserted (jobs.insert_job) — no tokens. Adding a name also tags every job already stored;
- the scoring model (`evaluate_job(via_recruiter=true, recruiter_reason=…)`).
jobs.via_recruiter: 'list' | 'detected' | 'cleared' (the user said "not a recruiter") | NULL.
Only the company field is matched (user decision): after dedup.normalise the company equals one of
the names, or starts with it as whole words ("Hays" matches "Hays Professional Solutions", not
"Haystack").
"""

from __future__ import annotations

import json
import sqlite3

from core.dedup import normalise

TAGGED = ("list", "detected")  # values that block automatic documents


def _names(raw: str | list[str]) -> list[str]:
    items = json.loads(raw) if isinstance(raw, str) else raw
    out = []
    for n in items:
        n = " ".join(str(n).split())
        if n and n.casefold() not in (x.casefold() for x in out):
            out.append(n)
    return out


def matches(company: str | None, names: list[str]) -> bool:
    c = normalise(company)
    if not c:
        return False
    for n in names:
        k = normalise(n)
        if k and (c == k or c.startswith(k + " ")):
            return True
    return False


def list_recruiters(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT r.id, r.names, r.note, r.created_at,
                  (SELECT COUNT(*) FROM jobs j WHERE j.recruiter_id = r.id AND j.via_recruiter = 'list') AS jobs
           FROM recruiters r ORDER BY r.names COLLATE NOCASE""").fetchall()
    return [{**dict(r), "names": _names(r["names"])} for r in rows]


def find(conn: sqlite3.Connection, company: str | None) -> dict | None:
    """The list entry a company belongs to, or None."""
    for r in conn.execute("SELECT id, names FROM recruiters ORDER BY id"):
        if matches(company, _names(r["names"])):
            return {"id": r["id"], "names": _names(r["names"])}
    return None


def tag_new_job(conn: sqlite3.Connection, job_id: int, company: str | None) -> bool:
    """Called by jobs.insert_job: tag a freshly stored job whose company is on the list."""
    hit = find(conn, company)
    if hit:
        conn.execute("UPDATE jobs SET via_recruiter = 'list', recruiter_id = ?, recruiter_reason = ? WHERE id = ?",
                     (hit["id"], f"on your recruiter list ({hit['names'][0]})", job_id))
    return bool(hit)


def add(conn: sqlite3.Connection, names: list[str], note: str | None = None) -> dict:
    """Add an agency (name + other spellings) and tag every stored job of it right away.
    Jobs the user cleared ("not a recruiter") stay cleared. Returns {id, names, tagged: [jobs]}."""
    clean = _names(names)
    if not clean:
        raise ValueError("give the recruiter's name")
    if any(not normalise(n) for n in clean):
        raise ValueError("a name needs at least one letter or digit")
    for r in list_recruiters(conn):
        if any(normalise(n) == normalise(m) for n in clean for m in r["names"]):
            raise ValueError(f"{r['names'][0]} is already on the list")
    rid = conn.execute("INSERT INTO recruiters (names, note) VALUES (?, ?)",
                       (json.dumps(clean, ensure_ascii=False), (note or "").strip() or None)).lastrowid
    tagged = retag(conn, rid)
    conn.commit()
    return {"id": rid, "names": clean, "tagged": tagged}


def retag(conn: sqlite3.Connection, recruiter_id: int) -> list[dict]:
    """Tag the stored jobs whose company matches this entry (a model's 'detected' becomes 'list')."""
    row = conn.execute("SELECT names FROM recruiters WHERE id = ?", (recruiter_id,)).fetchone()
    if row is None:
        raise ValueError(f"recruiter {recruiter_id} not found")
    names = _names(row["names"])
    tagged = []
    for j in conn.execute("""SELECT id, title, company, status FROM jobs
                             WHERE company IS NOT NULL AND COALESCE(via_recruiter, '') NOT IN ('cleared', 'list')"""):
        if matches(j["company"], names):
            conn.execute("""UPDATE jobs SET via_recruiter = 'list', recruiter_id = ?, recruiter_reason = ?,
                            recruiter_seen = 0, updated_at = datetime('now') WHERE id = ?""",
                         (recruiter_id, f"on your recruiter list ({names[0]})", j["id"]))
            tagged.append(dict(j))
    return tagged


def update(conn: sqlite3.Connection, recruiter_id: int, names: list[str], note: str | None = None) -> dict:
    clean = _names(names)
    if not clean:
        raise ValueError("give the recruiter's name")
    if conn.execute("UPDATE recruiters SET names = ?, note = ? WHERE id = ?",
                    (json.dumps(clean, ensure_ascii=False), (note or "").strip() or None, recruiter_id)).rowcount == 0:
        raise ValueError(f"recruiter {recruiter_id} not found")
    _untag(conn, recruiter_id)
    tagged = retag(conn, recruiter_id)
    conn.commit()
    return {"id": recruiter_id, "names": clean, "tagged": tagged}


def remove(conn: sqlite3.Connection, recruiter_id: int) -> int:
    """Delete the entry; its 'list' badges go (the model's 'detected' ones stay). Returns jobs untagged."""
    n = _untag(conn, recruiter_id)
    if conn.execute("DELETE FROM recruiters WHERE id = ?", (recruiter_id,)).rowcount == 0:
        raise ValueError(f"recruiter {recruiter_id} not found")
    conn.commit()
    return n


def _untag(conn: sqlite3.Connection, recruiter_id: int) -> int:
    return conn.execute("""UPDATE jobs SET via_recruiter = NULL, recruiter_id = NULL, recruiter_reason = NULL
                           WHERE recruiter_id = ? AND via_recruiter = 'list'""", (recruiter_id,)).rowcount


def mark_detected(conn: sqlite3.Connection, job_id: int, reason: str) -> None:
    """The scoring model found the posting is by a recruiter / for a client (evaluate_job). A job
    the user cleared, or one already on the list, keeps its state."""
    conn.execute("""UPDATE jobs SET via_recruiter = 'detected', recruiter_reason = ?, recruiter_seen = 0
                    WHERE id = ? AND via_recruiter IS NULL""", ((reason or "").strip()[:300] or "recruiter", job_id))


def clear(conn: sqlite3.Connection, job_id: int) -> None:
    """The user: "not a recruiter" — the job counts like any other again and is never re-tagged."""
    if conn.execute("""UPDATE jobs SET via_recruiter = 'cleared', recruiter_id = NULL, updated_at = datetime('now')
                       WHERE id = ?""", (job_id,)).rowcount == 0:
        raise ValueError(f"job {job_id} not found")
    conn.execute("""INSERT INTO status_history (job_id, from_status, to_status, note, changed_by)
                    SELECT id, status, status, 'not a recruiter', 'user' FROM jobs WHERE id = ?""", (job_id,))
    conn.commit()
