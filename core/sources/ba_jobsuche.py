"""Bundesagentur für Arbeit Jobsuche (public REST API).

Verified live on 2026-10-15: search is /pc/v6/jobs (v4 search returns 403); details are
/pc/v4/jobdetails/{base64(referenznummer)} (no v6 details path). Header X-API-Key: jobboerse-jobsuche.
"""

from __future__ import annotations

import base64
import math

from core.models import JobPosting, SearchFilter
from core.sources.base import PoliteClient, SourceError, register

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
JOB_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"
_ARBEITSZEIT = {"full_time": "vz", "part_time": "tz", "minijob": "mj"}


def arbeitszeit_param(f: SearchFilter) -> str | None:
    codes = [_ARBEITSZEIT[t] for t in f.employment_types if t in _ARBEITSZEIT]
    # BA treats the list as OR, so "ho" only narrows anything when on-site is not wanted.
    if "remote" in f.work_modes and "onsite" not in f.work_modes:
        codes.append("ho")
    return ";".join(dict.fromkeys(codes)) or None


@register
class BaJobsuche:
    key = "ba_jobsuche"

    def __init__(self):
        self.last_errors: list[dict] = []
        self._http: PoliteClient | None = None

    @property
    def http(self) -> PoliteClient:
        if self._http is None:
            self._http = PoliteClient(self.key, headers={"X-API-Key": "jobboerse-jobsuche"})
        return self._http

    def search(self, f: SearchFilter, limit: int) -> list[JobPosting]:
        self.last_errors = []
        out: dict[str, JobPosting] = {}
        spare: list[JobPosting] = []  # beyond a keyword's share; used if other keywords find too few
        share = math.ceil(limit / max(1, len(f.keywords)))
        for keyword in f.keywords:
            taken = 0
            params = {
                "was": keyword,
                "angebotsart": 1,
                "veroeffentlichtseit": min(f.max_age_days, 100),
                "page": 1,
                "size": 50,  # one page per keyword; trimmed to `limit` below
            }
            if f.location:
                params["wo"] = f.location
                params["umkreis"] = f.radius_km
            else:
                # Without "wo" BA mixes in EURES jobs from Austria etc.; "Deutschland" keeps it German.
                params["wo"] = "Deutschland"
            if az := arbeitszeit_param(f):
                params["arbeitszeit"] = az
            try:
                data = self.http.get_json(f"{BASE}/pc/v6/jobs", params)
            except SourceError as e:
                self.last_errors.append({"source": self.key, "message": f"'{keyword}': {e}"})
                if "403" in str(e) or "429" in str(e):
                    break  # blocked: don't keep hammering
                continue
            for item in data.get("ergebnisliste") or []:
                if _land(item) not in (None, "DEUTSCHLAND"):
                    continue  # user is searching in Germany only
                p = self._to_posting(item)
                if not p or p.source_job_id in out:
                    continue
                if taken < share:
                    out[p.source_job_id] = p
                    taken += 1
                else:
                    spare.append(p)
        for p in spare:
            if len(out) >= limit:
                break
            out.setdefault(p.source_job_id, p)
        if not out and self.last_errors:
            raise SourceError("; ".join(e["message"] for e in self.last_errors))
        return list(out.values())[:limit]

    def fetch_details(self, job: JobPosting) -> JobPosting:
        code = base64.b64encode(job.source_job_id.encode()).decode()
        d = self.http.get_json(f"{BASE}/pc/v4/jobdetails/{code}")
        job.description = d.get("stellenangebotsBeschreibung") or job.description
        job.salary_text = job.salary_text or _salary_text(d)
        partner = d.get("allianzpartnerUrl")
        if partner and job.description and partner not in job.description:
            job.description += f"\n\nOriginal-Anzeige: {partner}"
        return job

    def _to_posting(self, item: dict) -> JobPosting | None:
        ref = item.get("referenznummer") or item.get("refnr")
        title = item.get("stellenangebotsTitel") or item.get("titel")
        if not ref or not title:
            return None
        return JobPosting(
            source=self.key,
            source_job_id=ref,
            url=JOB_URL.format(ref=ref),
            title=title,
            company=item.get("firma") or item.get("arbeitgeber"),
            location=_location(item),
            posted_at=item.get("datumErsteVeroeffentlichung"),
            employment_type=_employment(item),
            salary_text=_salary_text(item),
        )


def _land(item: dict) -> str | None:
    for loc in item.get("stellenlokationen") or []:
        if land := (loc.get("adresse") or {}).get("land"):
            return land
    return None


def _location(item: dict) -> str | None:
    for loc in item.get("stellenlokationen") or []:
        a = loc.get("adresse") or {}
        if a.get("ort"):
            land = a.get("land")
            return a["ort"] + ("" if land in (None, "DEUTSCHLAND") else f", {land.title()}")
    return None


def _employment(item: dict) -> str | None:
    if item.get("istGeringfuegigeBeschaeftigung"):
        return "minijob"
    if item.get("arbeitszeitVollzeit"):
        return "full_time"
    if any(item.get(k) for k in ("arbeitszeitTeilzeitVormittag", "arbeitszeitTeilzeitNachmittag",
                                 "arbeitszeitTeilzeitAbend", "arbeitszeitTeilzeitFlexibel")):
        return "part_time"
    return None


def _salary_text(d: dict) -> str | None:
    if d.get("verguetungsangabe") in (None, "KEINE_ANGABEN"):
        return None
    amount = d.get("festgehalt") or d.get("verguetung")
    if not amount:
        return None
    period = {"MONATLICH": "pro Monat", "JAEHRLICH": "pro Jahr", "STUENDLICH": "pro Stunde"}.get(
        str(d.get("artDerVerguetung", "")).upper(), str(d.get("artDerVerguetung") or ""))
    return f"{amount} € {period}".strip()
