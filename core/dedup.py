"""Deduplication keys (CLAUDE.md §5): canonical URL + company|title|city fingerprint."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {
    "ref", "refid", "trk", "trkinfo", "trackingid", "gclid", "fbclid", "msclkid", "dclid",
    "mc_cid", "mc_eid", "_hsenc", "_hsmi", "igshid", "si", "originalsubdomain", "lipi",
    "midtoken", "midsig", "eid", "from", "vjk", "advn", "tk", "position", "pagenum",
    "sso", "token", "auth", "session", "sid",  # login tokens (e.g. Instaffo) must never be stored
}


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
              if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS]

    # Known boards: reduce to the stable job-id form.
    if host.endswith("linkedin.com"):
        job_id = dict(params).get("currentJobId")
        m = re.search(r"/jobs/view/(?:[^/]*?-)?(\d+)$", path)
        if m or job_id:
            return f"https://linkedin.com/jobs/view/{m.group(1) if m else job_id}"
    if "indeed." in host:
        jk = dict(params).get("jk")
        if jk:
            return f"https://{host}/viewjob?jk={jk}"
    if "glassdoor." in host:
        jl = dict(params).get("jl")
        if jl:
            return f"https://{host}/job-listing?jl={jl}"
    if host.endswith("arbeitsagentur.de"):
        m = re.search(r"/jobsuche/jobdetail/([^/]+)$", path)
        if m:
            return f"https://arbeitsagentur.de/jobsuche/jobdetail/{m.group(1)}"
    # Phase 9 (email alerts), patterns from the boards' public job URLs; not yet seen in the
    # user's inbox — verify when the first StepStone/XING alert arrives.
    if host.endswith("stepstone.de"):
        m = re.search(r"/stellenangebote--.*?-(\d{5,})-inline(?:\.html)?$", path) or re.search(r"/job/(\d{5,})", path)
        if m:
            return f"https://stepstone.de/stellenangebote--{m.group(1)}"
    if host.endswith("instaffo.com"):
        m = re.search(r"/candidate/job/([0-9a-f-]{36})$", path)
        if m:
            return f"https://app.instaffo.com/candidate/job/{m.group(1)}"
    if host.endswith("xing.com"):
        m = re.search(r"/jobs/(?:[^/]*?-)?(\d{5,})$", path)
        if m:
            return f"https://xing.com/jobs/{m.group(1)}"

    query = urlencode(sorted(params))
    return urlunsplit(("https", host, path, query, ""))


_GENDER_RE = re.compile(
    r"\(\s*(?:[mwfdx]\s*/\s*){1,3}[mwfdx*]\s*\)|\(\s*all\s+genders?\s*\)|\(\s*gn\*?\s*\)|\(\s*w\*?m\*?d\*?\s*\)",
    re.IGNORECASE,
)
_LEGAL_RE = re.compile(r"\b(?:gmbh\s*&\s*co\.?\s*kg(?:aa)?|gmbh|mbh|ag|se|kgaa|kg|ug|e\.?\s?v\.?|ltd|inc|llc)\b\.?",
                       re.IGNORECASE)


def normalise(text: str | None) -> str:
    s = (text or "").casefold()
    s = _GENDER_RE.sub(" ", s)
    s = _LEGAL_RE.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s)          # punctuation (keeps umlauts and ß)
    return re.sub(r"\s+", " ", s).strip()


def normalise_city(location: str | None) -> str:
    first = (location or "").split(",")[0]
    first = re.sub(r"\b\d{4,5}\b", " ", first)  # postal codes
    return normalise(first)


def fingerprint(company: str | None, title: str, location: str | None, canonical: str = "") -> str:
    company_n = normalise(company)
    if not company_n:
        # Without a company the title+city key would merge unrelated jobs; fall back to the URL.
        return hashlib.sha1(f"nocompany|{canonical}".encode()).hexdigest()
    key = f"{company_n}|{normalise(title)}|{normalise_city(location)}"
    return hashlib.sha1(key.encode()).hexdigest()
