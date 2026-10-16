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


def keyword_match(text: str, keywords: list[str]) -> bool:
    t = text.casefold()
    return any(k.casefold() in t for k in keywords)
