"""Jobicy remote-jobs API (https://jobicy.com/jobs-rss-feed; user decision 2026-10-25).

One feed of the last 7 days (≤ 200 jobs per page, MAX_PAGES pages), fetched once and cached for
6 h (FeedCache; Jobicy asks for at most one pass per hour). Keywords and target countries are
matched here, so every filter reuses the same download: a country target keeps jobs whose jobGeo
names it, its region ('Europe', 'EMEA', 'LATAM', …) or 'Anywhere'.

Terms: Jobicy is shown as the source and apply links stay Jobicy's job URL; JobHunter keeps the
jobs local and never republishes them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import countries
from core.models import JobPosting, SearchFilter
from core.sources.base import FeedCache, PoliteClient, SourceError, html_to_text, keyword_match, register
from core.sources.himalayas import _salary_text

API = "https://jobicy.com/api/v2/remote-jobs"
MAX_PAGES = 3
_TYPES = {"full-time": "full_time", "part-time": "part_time", "internship": "internship",
          "contract": "contract", "freelance": "freelance"}


@register
class Jobicy:
    key = "jobicy"
    countries = None
    remote_only = True

    def __init__(self):
        self.last_errors: list[dict] = []
        self._http: PoliteClient | None = None
        self.cache = FeedCache(self.key)

    @property
    def http(self) -> PoliteClient:
        if self._http is None:
            self._http = PoliteClient(self.key)
        return self._http

    def _feed(self) -> list[dict]:
        def load() -> list[dict]:
            jobs, cursor = [], None
            for _ in range(MAX_PAGES):
                params = {"count": 200} | ({"cursor": cursor} if cursor else {})
                try:
                    data = self.http.get_json(API, params)
                except SourceError:
                    if not jobs:
                        raise
                    break
                jobs += data.get("jobs") or []
                cursor = data.get("nextCursor")
                if not data.get("hasMore") or not cursor:
                    break
            return jobs
        return self.cache.fetch(API, load)

    def search(self, f: SearchFilter, limit: int) -> list[JobPosting]:
        self.last_errors = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=f.max_age_days)
        out: list[JobPosting] = []
        for item in self._feed():
            title = item.get("jobTitle") or ""
            if not item.get("url") or not keyword_match(title, f.keywords):
                continue
            if not countries.geo_matches(item.get("jobGeo"), f.countries):
                continue
            try:
                posted = datetime.fromisoformat(item.get("pubDate") or "")
            except ValueError:
                continue
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
            if posted < cutoff:
                continue
            out.append(self._to_posting(item, posted))
            if len(out) >= limit:
                break
        return out

    def fetch_details(self, job: JobPosting) -> JobPosting:
        return job

    def _to_posting(self, item: dict, posted: datetime) -> JobPosting:
        types = [_TYPES.get(str(t).casefold()) for t in item.get("jobType") or []]
        types = [t for t in types if t]
        geo = (item.get("jobGeo") or "").strip()
        return JobPosting(
            source=self.key,
            source_job_id=str(item.get("id") or item["url"]),
            url=item["url"],
            title=item["jobTitle"],
            company=item.get("companyName"),
            location="Remote" + (f" ({geo})" if geo and geo.casefold() != "anywhere" else ", worldwide"),
            description=html_to_text(item.get("jobDescription")),
            posted_at=posted.date().isoformat(),
            work_mode="remote",
            employment_type=types[0] if types else None,
            salary_text=_salary_text(item.get("salaryMin"), item.get("salaryMax"), item.get("salaryCurrency"),
                                     item.get("salaryPeriod")),
        )
