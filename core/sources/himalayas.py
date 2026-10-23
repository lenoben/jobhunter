"""Himalayas remote-jobs API (https://himalayas.app/api; user decision 2026-10-25).

Remote jobs only, from the search endpoint: one query per keyword (≤ MAX_QUERIES) and target,
`country=<ISO-2>` for a country target (remote jobs open to people there), `worldwide=true` for
`remote` / `worldwide`. Only jobs from the last 7 days are kept (user, 2026-10-25: the board is
huge), or fewer when the filter's max_age_days is smaller.

Terms: apply links stay Himalayas' applicationLink, Himalayas is shown as the source, and the jobs
are never passed on to other boards: JobHunter keeps them local. Optional free key
HIMALAYAS_API_KEY in .env (R3); without one, requests share the public allowance. Each query is
cached for 6 h (FeedCache).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from core import countries
from core.models import JobPosting, SearchFilter
from core.sources.base import FeedCache, PoliteClient, html_to_text, keyword_match, register

API = "https://himalayas.app/jobs/api/search"
MAX_AGE_DAYS = 7
MAX_QUERIES = 3
MAX_PAGES = 2       # 20 jobs per page, newest first
_TYPES = {"full time": "full_time", "part time": "part_time", "intern": "internship",
          "contractor": "freelance", "temporary": "contract"}


@register
class Himalayas:
    key = "himalayas"
    countries = None      # remote jobs for any country target
    remote_only = True

    def __init__(self):
        self.last_errors: list[dict] = []
        self._http: PoliteClient | None = None
        self.cache = FeedCache(self.key)

    @property
    def http(self) -> PoliteClient:
        if self._http is None:
            from dotenv import load_dotenv
            from core.db import ROOT
            load_dotenv(ROOT / ".env")
            key = os.environ.get("HIMALAYAS_API_KEY", "").strip()
            self._http = PoliteClient(self.key, headers={"Authorization": f"Bearer {key}"} if key else None)
        return self._http

    @staticmethod
    def targets(f: SearchFilter) -> list[dict]:
        out = []
        if countries.REMOTE in f.countries or countries.WORLDWIDE in f.countries:
            out.append({"worldwide": "true"})
        out += [{"country": iso} for c in f.countries if (iso := countries.iso2(c))]
        return out

    def search(self, f: SearchFilter, limit: int) -> list[JobPosting]:
        self.last_errors = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=min(f.max_age_days, MAX_AGE_DAYS))
        out: dict[str, JobPosting] = {}
        for target in self.targets(f):
            for kw in f.keywords[:MAX_QUERIES]:
                for page in range(1, MAX_PAGES + 1):
                    params = {"q": kw, "sort": "recent", "page": page, **target}
                    data = self.cache.fetch(f"{API}?{urlencode(params)}", lambda: self.http.get_json(API, params))
                    jobs = data.get("jobs") or []
                    older = False
                    for item in jobs:
                        posted = datetime.fromtimestamp(int(item.get("pubDate") or 0), timezone.utc)
                        if posted < cutoff:
                            older = True
                            continue
                        p = self._to_posting(item, posted)
                        if p and p.url not in out and keyword_match(p.title, f.keywords):
                            out[p.url] = p
                            if len(out) >= limit:
                                return list(out.values())
                    if older or len(jobs) < 20:
                        break
        return list(out.values())

    def fetch_details(self, job: JobPosting) -> JobPosting:
        return job  # the search result already has the full description

    def _to_posting(self, item: dict, posted: datetime) -> JobPosting | None:
        url = item.get("applicationLink") or item.get("guid")
        if not url or not item.get("title"):
            return None
        places = item.get("locationRestrictions") or []
        return JobPosting(
            source=self.key,
            source_job_id=item.get("guid"),
            url=url,
            title=item["title"],
            company=item.get("companyName"),
            location="Remote" + (f" ({', '.join(places)})" if places else ", worldwide"),
            description=html_to_text(item.get("description")),
            posted_at=posted.date().isoformat(),
            work_mode="remote",
            employment_type=_TYPES.get((item.get("employmentType") or "").casefold()),
            salary_text=_salary_text(item.get("minSalary"), item.get("maxSalary"), item.get("currency"),
                                     item.get("salaryPeriod")),
        )


def _salary_text(lo, hi, currency, period) -> str | None:
    """Shared with Jobicy: 'min - max CUR per year' in the form the §5a salary parser reads."""
    amounts = [str(int(v)) for v in (lo, hi) if v]
    if not amounts:
        return None
    interval = {"annual": "per year", "yearly": "per year", "monthly": "per month", "month": "per month",
                "hourly": "per hour", "hour": "per hour"}.get(str(period or "").casefold(), "")
    return f"{' - '.join(amounts)} {currency or ''} {interval}".replace("  ", " ").strip()
