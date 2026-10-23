"""Arbeitnow public job-board API. One shared feed (newest first); keywords/location are matched
client-side, so pages are cached for the process to avoid refetching them for every filter."""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from core.models import JobPosting, SearchFilter
from core.sources.base import PoliteClient, SourceError, html_to_text, keyword_match, register

API = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 5
CACHE_TTL_S = 600
GERMAN_HOSTS = {"arbeitnow.com", "arbeitnow.de"}
_JOB_TYPES = {
    "full time": "full_time", "vollzeit": "full_time", "part time": "part_time", "teilzeit": "part_time",
    "internship": "internship", "praktikum": "internship", "werkstudent": "working_student",
    "working student": "working_student", "freelance": "freelance", "minijob": "minijob",
    "contract": "contract",
}


_NON_DE = re.compile(
    r"\b(united kingdom|england|scotland|wales|london|uk|ireland|netherlands|niederlande|austria|"
    r"österreich|switzerland|schweiz|france|frankreich|spain|spanien|poland|polen|portugal|italy|"
    r"italien|usa|united states|canada|"
    r"z[uü]rich|geneva|genf|gen[eè]ve|basel|bern|lausanne|zug|luzern|lucerne|vienna|wien|graz|linz|"
    r"salzburg|amsterdam|rotterdam|utrecht|eindhoven|paris|lyon|madrid|barcelona|lisbon|lissabon|"
    r"warsaw|warschau|krak[oó]w|wroc[lł]aw|prague|prag|brno|dublin|copenhagen|kopenhagen|stockholm|"
    r"oslo|helsinki|brussels|br[uü]ssel|luxembourg|luxemburg|milan|mailand|budapest|bucharest|"
    r"bukarest|tallinn|riga|vilnius|sofia|athens|athen|belgrade|zagreb|ljubljana)\b", re.IGNORECASE)


_DE = re.compile(
    r"\b(deutschland|germany|baden-w[uü]rttemberg|bayern|bavaria|berlin|brandenburg|bremen|hamburg|"
    r"hessen|hesse|mecklenburg|niedersachsen|lower saxony|nordrhein-westfalen|north rhine-westphalia|"
    r"rheinland-pfalz|rhineland-palatinate|saarland|sachsen|saxony|sachsen-anhalt|saxony-anhalt|"
    r"schleswig-holstein|th[uü]ringen|thuringia)\b", re.IGNORECASE)


def _in_germany(item: dict) -> bool:
    """The feed also carries arbeitnow.co.uk / arbeitnow.ch etc. and other non-German jobs; keep
    German or unspecified locations on the German sites only."""
    host = urlsplit(item.get("url") or "").hostname or ""
    if host.removeprefix("www.") not in GERMAN_HOSTS:
        return False
    loc = (item.get("location") or "").strip()
    if not loc or _DE.search(loc):
        return True
    if "," in loc:  # "City, Region[, Country]" with no German region/country → abroad
        return False
    return not _NON_DE.search(loc)  # single city name: reject known foreign cities


@register
class Arbeitnow:
    key = "arbeitnow"
    countries = frozenset({"germany"})  # German boards only (core/countries.py)

    def __init__(self):
        self.last_errors: list[dict] = []
        self._http: PoliteClient | None = None
        self._pages: dict[int, tuple[float, dict]] = {}

    @property
    def http(self) -> PoliteClient:
        if self._http is None:
            self._http = PoliteClient(self.key)
        return self._http

    def _page(self, n: int) -> dict:
        cached = self._pages.get(n)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
            return cached[1]
        data = self.http.get_json(API, {"page": n})
        self._pages[n] = (time.monotonic(), data)
        return data

    def search(self, f: SearchFilter, limit: int) -> list[JobPosting]:
        self.last_errors = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=f.max_age_days)
        out: list[JobPosting] = []
        for n in range(1, MAX_PAGES + 1):
            try:
                data = self._page(n)
            except SourceError as e:
                if not out and n == 1:
                    raise
                self.last_errors.append({"source": self.key, "message": str(e)})
                break
            items = data.get("data") or []
            too_old = False
            for item in items:
                posted = datetime.fromtimestamp(int(item.get("created_at") or 0), timezone.utc)
                if posted < cutoff:
                    too_old = True
                    continue
                if not self._matches(item, f):
                    continue
                out.append(self._to_posting(item, posted))
                if len(out) >= limit:
                    return out
            if too_old or not (data.get("links") or {}).get("next"):
                break
        return out

    def fetch_details(self, job: JobPosting) -> JobPosting:
        return job  # the feed already contains the full description

    @staticmethod
    def _matches(item: dict, f: SearchFilter) -> bool:
        text = " ".join([item.get("title") or "", " ".join(item.get("tags") or [])])
        if not keyword_match(text, f.keywords):
            return False
        if not _in_germany(item):
            return False
        if f.location:
            loc = (item.get("location") or "").casefold()
            if f.location.casefold() not in loc and not item.get("remote"):
                return False
        return True

    def _to_posting(self, item: dict, posted: datetime) -> JobPosting:
        types = [_JOB_TYPES.get(t.casefold()) for t in item.get("job_types") or []]
        types = [t for t in types if t]
        return JobPosting(
            source=self.key,
            source_job_id=item.get("slug"),
            url=item["url"],
            title=item["title"],
            company=item.get("company_name"),
            location=item.get("location") or None,
            description=html_to_text(item.get("description")),
            posted_at=posted.date().isoformat(),
            work_mode="remote" if item.get("remote") else None,
            employment_type=types[0] if types else None,
        )
