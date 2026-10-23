"""Source protocol, registry and polite-HTTP helpers shared by all adapters (CLAUDE.md §5, R6)."""

from __future__ import annotations

import html
import re
import time
from typing import Protocol, runtime_checkable

import httpx

from core.models import JobPosting, SearchFilter

USER_AGENT = "JobHunter/0.1 (personal job search; low volume)"
MIN_INTERVAL_S = 3.0  # R6: at least 3 s between requests per site


class SourceError(Exception):
    """A source failed or blocked us. The search records it and continues with other sources."""


@runtime_checkable
class Source(Protocol):
    key: str
    # Per-call errors that did not abort the whole source (e.g. one jobspy site blocked).
    last_errors: list[dict]
    # Optional class attributes, read with getattr (core/search.py covers()):
    #   countries: frozenset[str] | None — target countries the source covers (None = all)
    #   remote_only: bool — only remote jobs, so skipped when the filter doesn't want remote

    def search(self, f: SearchFilter, limit: int) -> list[JobPosting]: ...
    def fetch_details(self, job: JobPosting) -> JobPosting: ...


SOURCES: dict[str, Source] = {}


def register(cls):
    """Class decorator: instantiate the adapter and add it to SOURCES under its key."""
    instance = cls()
    SOURCES[instance.key] = instance
    return cls


class Throttle:
    """Keeps at least `interval` seconds between calls for one site."""

    def __init__(self, interval: float = MIN_INTERVAL_S):
        self.interval = interval
        self._last = 0.0

    def wait(self) -> None:
        delay = self._last + self.interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


class PoliteClient:
    """httpx client with per-site throttling and back-off on 429/403 (R6)."""

    def __init__(self, site: str, headers: dict | None = None, interval: float = MIN_INTERVAL_S,
                 max_retries: int = 2):
        self.site = site
        self.throttle = Throttle(interval)
        self.max_retries = max_retries
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})},
            timeout=30, follow_redirects=True,
        )

    def get_json(self, url: str, params: dict | None = None) -> dict:
        for attempt in range(self.max_retries + 1):
            self.throttle.wait()
            try:
                r = self.client.get(url, params=params)
            except httpx.HTTPError as e:
                if attempt == self.max_retries:
                    raise SourceError(f"{self.site}: network error: {e}") from None
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 429 and attempt < self.max_retries:
                time.sleep(_retry_after(r) or 15 * (attempt + 1))
                continue
            if r.status_code in (403, 429):
                raise SourceError(f"{self.site}: HTTP {r.status_code} (blocked or rate-limited)")
            if r.status_code >= 400:
                raise SourceError(f"{self.site}: HTTP {r.status_code} for {r.url}")
            return r.json()
        raise SourceError(f"{self.site}: gave up after {self.max_retries + 1} attempts")


FEED_MIN_INTERVAL_H = 6  # user decision 2026-10-25


class FeedCache:
    """Responses of public APIs with daily limits (Himalayas, Jobicy), kept on disk in
    data/cache/<source>/ and reused for FEED_MIN_INTERVAL_H hours: however often runs start (the
    user may schedule them every few hours, or press Run now), each URL is requested at most once
    in that window. Jobs already stored are dropped by dedup (R8), so a reused response costs
    nothing."""

    def __init__(self, source: str, hours: float = FEED_MIN_INTERVAL_H):
        self.source, self.max_age_s = source, hours * 3600
        self.hits = 0

    def _dir(self):
        from core.db import db_path
        return db_path().parent / "cache" / self.source

    def fetch(self, key: str, load):
        """The cached value for `key` if younger than the interval, else load() (stored on success)."""
        import hashlib
        import json
        path = self._dir() / f"{hashlib.sha1(key.encode()).hexdigest()[:20]}.json"
        now = time.time()
        if path.exists() and now - path.stat().st_mtime < self.max_age_s:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                self.hits += 1
                return value
            except ValueError:
                pass
        value = load()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        for old in path.parent.glob("*.json"):  # keep the folder small
            if now - old.stat().st_mtime > 2 * 86400:
                old.unlink(missing_ok=True)
        return value


def _retry_after(r: httpx.Response) -> float | None:
    try:
        return min(float(r.headers.get("Retry-After", "")), 120.0)
    except ValueError:
        return None


def html_to_text(raw: str | None) -> str | None:
    if not raw:
        return raw
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", raw)
    s = re.sub(r"(?i)<li[^>]*>", "• ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", s).strip()


def _keyword_re(kw: str) -> re.Pattern | None:
    tokens = re.split(r"[\s\-_/]+", kw.casefold().strip())
    tokens = [t for t in tokens if t]
    # starts at a word boundary ("Go Developer" ≠ "Django Developer"); a space may be missing
    return re.compile(r"(?<!\w)" + r" ?".join(map(re.escape, tokens))) if tokens else None


def keyword_match(text: str, keywords: list[str]) -> bool:
    """Case-insensitive, and hyphen/space variants match (2026-10-18: such titles were missed):
    "Full Stack Developer" matches "Full-Stack Developer" and "Fullstack Developer"; "Fullstack"
    matches "Full-Stack"; "Softwareentwickler" matches "Software-Entwickler"."""
    t = text.casefold()
    spaced = re.sub(r"[\s\-_/]+", " ", t)     # "full-stack" → "full stack"
    joined = re.sub(r"(?<=\w)-(?=\w)", "", t)  # "software-entwickler" → "softwareentwickler"
    joined = re.sub(r"[\s_/]+", " ", joined)
    for kw in keywords:
        pattern = _keyword_re(kw)
        if pattern and (pattern.search(spaced) or pattern.search(joined)):
            return True
    return False
