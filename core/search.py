"""Search pipeline: adapters → Python-side filters → dedup (R8) → details → §5a checks → insert."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from core import checks, jobs
from core.db import get_settings
from core.dedup import canonical_url, fingerprint
from core.models import JobPosting, SearchFilter
from core.sources import SOURCES, SourceError

FREELANCE_TYPES = {"freelance"}


@dataclass
class SearchResult:
    found: int = 0
    new: list[JobPosting] = field(default_factory=list)       # status new or needs_attention
    skipped: list[JobPosting] = field(default_factory=list)   # stored as skipped (still "seen")
    duplicates: int = 0
    too_old: int = 0
    errors: list[dict] = field(default_factory=list)          # [{source, message}]


def prefilter(p: JobPosting, f: SearchFilter) -> str | None:
    """Reason to store the job as skipped without evaluation, or None."""
    title = p.title.casefold()
    for kw in f.exclude_keywords:
        if kw.casefold() in title:
            return f"excluded keyword in title: {kw}"
    if f.exclude_freelance and p.employment_type in FREELANCE_TYPES:
        return "freelance"
    if p.employment_type and p.employment_type not in f.employment_types and p.employment_type != "contract":
        return f"employment type {p.employment_type} not wanted"
    return None


def run_search(conn: sqlite3.Connection, f: SearchFilter, sources: list[str] | None = None,
               limit: int = 20, dry_run: bool = False, log: Callable[[str], None] = lambda _m: None) -> SearchResult:
    settings = get_settings(conn)
    threshold = float(settings.get("blue_card_salary_min", "45934.20"))
    cutoff = (date.today() - timedelta(days=f.max_age_days)).isoformat()
    result = SearchResult()
    batch_keys: set[str] = set()

    for key in sources or f.sources:
        adapter = SOURCES.get(key)
        if adapter is None:
            result.errors.append({"source": key, "message": "unknown source"})
            continue
        log(f"[{key}] searching …")
        if hasattr(adapter, "dry_run"):
            adapter.dry_run = dry_run  # e.g. email_alerts must not mark mails processed in a dry run
        try:
            postings = adapter.search(f, limit)
        except SourceError as e:
            result.errors.append({"source": key, "message": str(e)})
            log(f"[{key}] failed: {e}")
            continue
        except Exception as e:  # an adapter bug must not kill the whole run
            result.errors.append({"source": key, "message": f"{type(e).__name__}: {e}"})
            log(f"[{key}] crashed: {e}")
            continue
        result.errors.extend(adapter.last_errors)
        log(f"[{key}] {len(postings)} postings")

        for p in postings:
            result.found += 1
            if p.posted_at and p.posted_at[:10] < cutoff:
                result.too_old += 1
                continue
            p.canonical_url = canonical_url(p.url)
            p.fingerprint = fingerprint(p.company, p.title, p.location, p.canonical_url)
            if (p.canonical_url in batch_keys or p.fingerprint in batch_keys
                    or jobs.find_seen(conn, p.canonical_url, p.fingerprint)):
                result.duplicates += 1
                continue
            batch_keys.update((p.canonical_url, p.fingerprint))
            p.filter_id = f.id

            note = None
            if reason := prefilter(p, f):
                p.status, note = "skipped", reason
                result.skipped.append(p)
            else:
                if not p.description:
                    try:
                        p = adapter.fetch_details(p)
                    except SourceError as e:
                        result.errors.append({"source": key, "message": f"details {p.source_job_id}: {e}"})
                note = _screen(p, threshold)
                result.new.append(p)

            if not dry_run:
                try:
                    p.id = jobs.insert_job(conn, p, note)
                except sqlite3.IntegrityError:  # raced with another insert of the same URL
                    result.duplicates += 1
                    (result.skipped if p.status == "skipped" else result.new).remove(p)
                    continue
        if not dry_run:
            conn.commit()
    return result


def _screen(p: JobPosting, threshold: float) -> str | None:
    """Apply §5a checks; sets salary fields and status. Returns a status_history note."""
    salary = checks.check_salary(p.salary_text, threshold)
    p.salary_annual_eur, p.salary_flag = salary.annual_eur, salary.flag
    notes = []
    if phrase := checks.check_work_authorization(p.title, p.description):
        p.status, p.attention_reason = "needs_attention", "work_authorization"
        notes.append(f'work_authorization: ad says "{phrase}"')
    if salary.flag == "below_blue_card_threshold":
        notes.append(f"below_blue_card_threshold: ≈ €{salary.annual_eur:,.0f}/year < €{threshold:,.2f}")
        if p.status != "needs_attention":
            p.status, p.attention_reason = "needs_attention", "below_blue_card_threshold"
    return "; ".join(notes) or None
