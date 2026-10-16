"""Indeed (DE), LinkedIn and Glassdoor via python-jobspy (scraping — R6 applies).
Google Jobs was removed on 2026-10-15 (user decision): it returned nothing for every filter.

Each site is scraped in its own call so one blocked site (LinkedIn often is) is recorded in
last_errors and the others still return. Results are kept small (≤ 20 per site per run).
"""

from __future__ import annotations

import math
import time

from core.models import JobPosting, SearchFilter
from core.sources.base import MIN_INTERVAL_S, SourceError, register

SITES = ["indeed", "linkedin", "glassdoor"]
MAX_PER_SITE = 20
# Sites that understand boolean OR in the search term get one combined query;
# the others get one query per keyword, capped to keep the request count low.
OR_SITES = {"indeed", "linkedin"}
MAX_QUERIES_PER_SITE = 2
_JOB_TYPES = {"fulltime": "full_time", "parttime": "part_time", "internship": "internship",
              "contract": "contract", "temporary": "contract"}


def _clean(v):
    """pandas NaN/NaT → None."""
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except TypeError:
        pass
    s = str(v)
    return None if s in ("nan", "NaT", "None", "") else v


@register
class JobSpySource:
    key = "jobspy"

    def __init__(self):
        self.last_errors: list[dict] = []
        self.sites = list(SITES)

    def search(self, f: SearchFilter, limit: int) -> list[JobPosting]:
        try:
            from jobspy import scrape_jobs
        except ImportError as e:
            raise SourceError(f"python-jobspy not installed: {e}") from None

        self.last_errors = []
        per_site = max(1, min(limit, MAX_PER_SITE))
        location = f.location or "Germany"
        out: dict[str, JobPosting] = {}
        first_call = True
        for site in self.sites:
            if site in OR_SITES:
                queries = [" OR ".join(f'"{k}"' for k in f.keywords)]
            else:
                queries = f.keywords[:MAX_QUERIES_PER_SITE]
            got = 0
            for q in queries:
                if got >= per_site:
                    break
                if not first_call:
                    time.sleep(MIN_INTERVAL_S)
                first_call = False
                kwargs = dict(
                    site_name=[site],
                    search_term=q,
                    location=location,
                    results_wanted=per_site - got,
                    hours_old=f.max_age_days * 24,
                    country_indeed="germany",
                    description_format="markdown",
                    linkedin_fetch_description=True,
                    verbose=0,
                )
                if f.location:
                    kwargs["distance"] = max(1, round(f.radius_km / 1.609))
                try:
                    df = scrape_jobs(**kwargs)
                except Exception as e:  # jobspy raises many types; a failing site must not stop the run
                    self.last_errors.append({"source": f"jobspy:{site}", "message": f"{type(e).__name__}: {e}"[:300]})
                    break
                for row in df.to_dict("records"):
                    p = self._to_posting(row, site)
                    if p and p.url not in out:
                        out[p.url] = p
                        got += 1
            else:
                if got == 0:  # jobspy only logs blocks (e.g. LinkedIn), so surface them here
                    self.last_errors.append({"source": f"jobspy:{site}",
                                             "message": "returned no results (blocked or nothing new)"})
        if not out and self.last_errors and len(self.last_errors) == len(self.sites):
            raise SourceError("all jobspy sites failed: " + "; ".join(e["message"] for e in self.last_errors))
        return list(out.values())

    def fetch_details(self, job: JobPosting) -> JobPosting:
        return job  # jobspy already returns descriptions where the site provides them

    def _to_posting(self, row: dict, site: str) -> JobPosting | None:
        url = _clean(row.get("job_url"))
        title = _clean(row.get("title"))
        if not url or not title:
            return None
        remote = _clean(row.get("is_remote"))
        posted = _clean(row.get("date_posted"))
        return JobPosting(
            source=self.key,
            source_job_id=_clean(row.get("id")) or f"{site}:{url}",
            url=str(url),
            title=str(title),
            company=_clean(row.get("company")),
            location=_clean(row.get("location")),
            description=_clean(row.get("description")),
            posted_at=str(posted)[:10] if posted else None,
            work_mode="remote" if remote is True else None,
            employment_type=_JOB_TYPES.get(str(_clean(row.get("job_type")) or "").split(",")[0].strip()),
            salary_text=_salary_text(row),
        )


def _salary_text(row: dict) -> str | None:
    lo, hi = _clean(row.get("min_amount")), _clean(row.get("max_amount"))
    if lo is None and hi is None:
        return None
    currency = _clean(row.get("currency")) or "EUR"
    raw_interval = str(_clean(row.get("interval")) or "")
    factor = {"weekly": 52, "daily": 220}.get(raw_interval, 1)  # the salary parser knows year/month/hour only
    interval = "per year" if factor != 1 else {"yearly": "per year", "monthly": "per month",
                                               "hourly": "per hour"}.get(raw_interval, "")
    amount = " - ".join(str(int(v * factor)) for v in (lo, hi) if v is not None)
    return f"{amount} {currency} {interval}".strip()
