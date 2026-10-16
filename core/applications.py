"""Applications: the documents for a job, notes.md, and the email-draft marker."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from pathlib import Path

from core import jobs
from core.db import ROOT

LETTER_FILES = {"de": "anschreiben.pdf", "en": "cover_letter.pdf"}  # legacy names (before 2026-10-16)

# Document file names (user request 2026-10-16): <Name>_<Job_title>_<Document>.pdf, e.g.
# Max_Mustermann_Backend_Developer_Lebenslauf.pdf. The suffix says what it is.
DOC_SUFFIXES = {("cv", "de"): "Lebenslauf", ("cv", "en"): "CV",
                ("letter", "de"): "Anschreiben", ("letter", "en"): "Cover_Letter"}
_LEGACY = {"cv.pdf": ("cv", None), "anschreiben.pdf": ("letter", "de"), "cover_letter.pdf": ("letter", "en")}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,200}\.pdf$")
_TRANSLIT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def _slug(text: str, max_len: int) -> str:
    text = re.sub(r"\(\s*(?:[mwfdxgn]\s*[/|*]?\s*){1,4}\)|\(\s*all\s+genders?\s*\)|\(\s*gn\*?\s*\)", " ", text or "",
                  flags=re.IGNORECASE)  # gender tags such as (m/w/d), (all gender)
    text = unicodedata.normalize("NFKD", text.translate(_TRANSLIT)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text[:max_len].rstrip("_")


def document_filename(person: str, job_title: str, kind: str, lang: str) -> str:
    """'Max Mustermann', 'Webentwickler React / Angular (m/w/d)', 'cv', 'de' →
    'Max_Mustermann_Webentwickler_React_Angular_Lebenslauf.pdf' (ASCII-safe for upload forms)."""
    parts = [p for p in (_slug(person, 60), _slug(job_title, 60), DOC_SUFFIXES[(kind, lang)]) if p]
    return "_".join(parts) + ".pdf"


def classify_document(name: str) -> tuple[str, str | None] | None:
    """('cv'|'letter', 'de'|'en'|None) for a generated document's file name, else None."""
    if name in _LEGACY:
        return _LEGACY[name]
    if not _SAFE_NAME.match(name):
        return None
    for (kind, lang), suffix in DOC_SUFFIXES.items():
        if name.endswith(f"_{suffix}.pdf"):
            return kind, lang
    return None


def list_documents(job_id: int) -> list[Path]:
    """The generated PDFs in output/<job_id>/, CV first."""
    d = output_dir(job_id)
    if not d.is_dir():
        return []
    docs = [p for p in d.iterdir() if p.is_file() and classify_document(p.name)]
    return sorted(docs, key=lambda p: (classify_document(p.name)[0] != "cv", p.name))
READY_FROM = ("shortlisted", "needs_attention", "docs_ready")  # evaluated first; re-saving is allowed


def output_root() -> Path:
    override = os.environ.get("JOBHUNTER_OUTPUT")
    return Path(override) if override else ROOT / "output"


def output_dir(job_id: int) -> Path:
    return output_root() / str(job_id)


def find_documents(job_id: int) -> tuple[Path | None, Path | None, str]:
    """(cv, letter, doc_language) as written by render_documents. Either may be None when the user
    asked for one document only; raises if there is neither."""
    d = output_dir(job_id)
    docs = list_documents(job_id)
    cvs = [p for p in docs if classify_document(p.name)[0] == "cv"]
    letters = [p for p in docs if classify_document(p.name)[0] == "letter"]
    if not cvs and not letters:
        raise ValueError(f"no documents for job {job_id} in {d}; call render_documents first")
    newest = lambda ps: max(ps, key=lambda p: p.stat().st_mtime) if ps else None  # noqa: E731
    cv, letter = newest(cvs), newest(letters)
    lang = next((classify_document(p.name)[1] for p in (letter, cv) if p and classify_document(p.name)[1]), None)
    if lang is None:
        content = d / "content.json"
        lang = json.loads(content.read_text(encoding="utf-8")).get("doc_language", "de") if content.exists() else "de"
    return cv, letter, lang


def rename_legacy_documents(conn: sqlite3.Connection, person: str) -> list[tuple[int, str, str]]:
    """One-off: cv.pdf / anschreiben.pdf / cover_letter.pdf → the named form; updates applications."""
    renamed = []
    root = output_root()
    if not root.is_dir():
        return renamed
    for d in root.iterdir():
        if not (d.is_dir() and d.name.isdigit()):
            continue
        job_id = int(d.name)
        row = conn.execute("SELECT title FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            continue
        content = d / "content.json"
        lang = json.loads(content.read_text(encoding="utf-8")).get("doc_language", "de") if content.exists() else "de"
        for old, (kind, old_lang) in _LEGACY.items():
            src = d / old
            if src.exists():
                dst = d / document_filename(person, row["title"], kind, old_lang or lang)
                src.replace(dst)
                renamed.append((job_id, old, dst.name))
        cv, letter, _ = find_documents(job_id) if list_documents(job_id) else (None, None, None)
        conn.execute("UPDATE applications SET cv_path = ?, letter_path = ? WHERE job_id = ?",
                     (str(cv) if cv else None, str(letter) if letter else None, job_id))
    conn.commit()
    return renamed


def get_application(conn: sqlite3.Connection, job_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    app = dict(row)
    app["inferred_facts"] = json.loads(app.get("inferred_facts") or "[]")
    return app


def save_application(conn: sqlite3.Connection, job_id: int, summary: str, interview_prep: str,
                     method: str) -> dict:
    """Create/update the applications row, write notes.md and set status docs_ready."""
    job = jobs.get_job(conn, job_id)
    if job["status"] not in READY_FROM:
        raise ValueError(f"job {job_id} has status {job['status']}; documents can't be saved for it")
    for name, value in (("summary", summary), ("interview_prep", interview_prep), ("method", method)):
        if not value or not value.strip():
            raise ValueError(f"{name} must not be empty")
    cv, letter, lang = find_documents(job_id)
    inferred = read_inferred(job_id)

    conn.execute(
        """INSERT INTO applications (job_id, cv_path, letter_path, doc_language, summary, interview_prep, method,
                                     inferred_facts, inferred_approved_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
           ON CONFLICT(job_id) DO UPDATE SET cv_path = excluded.cv_path, letter_path = excluded.letter_path,
             doc_language = excluded.doc_language, summary = excluded.summary,
             interview_prep = excluded.interview_prep, method = excluded.method,
             inferred_facts = excluded.inferred_facts, inferred_approved_at = NULL""",
        (job_id, str(cv) if cv else None, str(letter) if letter else None, lang, summary, interview_prep, method,
         json.dumps(inferred, ensure_ascii=False)))
    conn.execute("UPDATE jobs SET docs_requested = NULL WHERE id = ?", (job_id,))  # request fulfilled
    notes = output_dir(job_id) / "notes.md"
    notes.write_text(_notes_md(job, summary, interview_prep, method, lang, inferred), encoding="utf-8")
    if inferred:
        # R5/R9: documents with inferred facts wait for the user's approval (UI → docs_ready).
        listing = "; ".join(f"{f['text']} ({f['basis']})" for f in inferred)
        jobs.set_status(conn, job_id, "needs_attention", "claude", attention_reason="inferred_facts",
                        note=f"inferred_facts: {len(inferred)} to approve: {listing}"[:1000])
    elif job["status"] != "docs_ready":
        jobs.set_status(conn, job_id, "docs_ready", "claude", note=f"documents ({lang}) ready")
    conn.commit()
    return get_application(conn, job_id) | {"notes_path": str(notes)}


def read_inferred(job_id: int) -> list[dict]:
    """Inferred facts render_documents recorded in output/<job_id>/content.json."""
    path = output_dir(job_id) / "content.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("inferred") or []


def rejected_inferences(conn: sqlite3.Connection) -> list[dict]:
    """R9: statements the user rejected; they must never appear in documents again."""
    return [dict(r) for r in conn.execute(
        "SELECT text, basis, job_id, rejected_at FROM rejected_inferences ORDER BY id")]


def reject_inferred(conn: sqlite3.Connection, job_id: int, note: str | None = None,
                    changed_by: str = "user") -> None:
    """The user rejected the inferred facts: remember them (never reused) and send the job back
    to shortlisted so the next run re-renders without them."""
    app = get_application(conn, job_id)
    if app is None:
        raise ValueError(f"job {job_id} has no application")
    for f in app["inferred_facts"]:
        conn.execute("INSERT INTO rejected_inferences (text, basis, job_id) VALUES (?, ?, ?)",
                     (f["text"], f.get("basis"), job_id))
    jobs.set_status(conn, job_id, "shortlisted", changed_by,
                    note=f"inferred facts rejected{': ' + note if note else ''} — re-render without them")
    conn.commit()


def approve_inferred(conn: sqlite3.Connection, job_id: int, changed_by: str = "user") -> None:
    """The user accepted the inferred facts: documents become docs_ready. Only the user does this."""
    app = get_application(conn, job_id)
    if app is None:
        raise ValueError(f"job {job_id} has no application")
    conn.execute("UPDATE applications SET inferred_approved_at = datetime('now') WHERE job_id = ?", (job_id,))
    jobs.set_status(conn, job_id, "docs_ready", changed_by, note="inferred facts approved")
    conn.commit()


def mark_email_draft_saved(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("UPDATE applications SET email_draft_saved = 1 WHERE job_id = ?", (job_id,))
    conn.commit()


def _suggestions_md(items: list[dict]) -> str:
    """R11: small projects that would close a gap. Never part of the documents."""
    if not items:
        return ""
    rows = "\n".join(f"| {p['title']} | {p['scope']} | {p['days']} | {p['covers']} |" for p in items)
    return f"""
## Project ideas for the gaps (R11; not in the documents)
| Project | Scope | Days | Covers |
|---|---|---|---|
{rows}
"""


def _inferred_md(inferred: list[dict]) -> str:
    if not inferred:
        return ""
    rows = "\n".join(f"| {f['document']} | {f['where'] or '–'} | {f['text']} | {f['basis']} |" for f in inferred)
    return f"""
## ⚠️ Inferred facts — need your approval before you use these documents
Not stated in profile.yaml, but implied by it (R5/R9). Approve them, or have the documents re-rendered without them.

| Document | Where | Statement | Basis in your profile |
|---|---|---|---|
{rows}
"""


def _notes_md(job: dict, summary: str, interview_prep: str, method: str, lang: str,
              inferred: list[dict] = ()) -> str:
    salary = job["salary_text"] or "not stated"
    if job["salary_annual_eur"]:
        salary += f" (≈ €{job['salary_annual_eur']:,.0f}/year, {job['salary_flag']})"
    description = (job["description"] or "").strip() or "_(no description)_"
    return f"""# {job['title']} — {job['company'] or '?'}

| | |
|---|---|
| Location | {job['location'] or '?'} ({job['work_mode'] or 'unknown'}) |
| Employment | {job['employment_type'] or '?'} |
| Posting language / documents | {job['language'] or '?'} / {lang} |
| Salary | {salary} |
| Source | {job['source']} — {job['url']} |
| Apply | {job['apply_method'] or '?'}{(' — ' + job['apply_email']) if job['apply_email'] else ''} |
| How to submit | {method} |
| Fit score | {job['fit_score'] if job['fit_score'] is not None else '?'} |
{_inferred_md(list(inferred))}
## Fit
{job['fit_notes'] or '_(not evaluated)_'}
{_suggestions_md(job.get('project_suggestions') or [])}
## What was emphasised
{summary}

## Interview prep
{interview_prep}

## Posting snapshot
{description}
"""
