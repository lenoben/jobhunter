"""Jobs the user adds by hand (a posting link and/or the pasted text), and the full posting text
the user adds to an existing job, e.g. one from an email alert (user requests 2026-10-16).

The job then goes through the normal pipeline: §5a screening here, and Claude's evaluation (and
documents if the criteria are met) via `run.ps1 -Trigger single -JobId N`.
"""

from __future__ import annotations

import json
import re
import sqlite3
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

from core import checks, jobs
from core.db import get_settings
from core.dedup import canonical_url, fingerprint
from core.filters import load_filters
from core.models import JobPosting
from core.search import _screen
from core.sources.base import USER_AGENT, html_to_text, keyword_match

MAX_TEXT = 30_000
# Pages that need a login (or carry login tokens): never fetched — the user pastes the text.
NO_FETCH_HOSTS = ("linkedin.com", "instaffo.com", "xing.com")
_SALARY_LINE = re.compile(r"(gehalt|salary|vergütung|verguetung|brutto|gross|€|eur\b)", re.IGNORECASE)


class ManualJobError(ValueError):
    pass


def fetch_posting(url: str) -> dict:
    """Anonymous, single GET (no cookies, no login) of a public job page. Uses the page's
    schema.org JobPosting if present, else the page title + visible text."""
    host = (urlsplit(url).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in NO_FETCH_HOSTS):
        raise ManualJobError(f"{host} needs a login, so the page isn't fetched — paste the posting text instead")
    if host.endswith("smartrecruiters.com"):
        if (sr := _smartrecruiters(url)) is not None:
            return sr
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
            r = client.get(url)
    except httpx.HTTPError as e:
        raise ManualJobError(f"could not load the page ({type(e).__name__}) — paste the posting text instead") from None
    if r.status_code >= 400:
        raise ManualJobError(f"the page answered HTTP {r.status_code} — paste the posting text instead")
    page = r.text
    found = _parse_posting_page(page, str(r.url))
    found["apply_url"] = _apply_link_from_html(page, str(r.url))
    return found


def _parse_posting_page(page: str, url: str) -> dict:
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for item in _walk_ld(data):
            if item.get("@type") == "JobPosting":
                org = item.get("hiringOrganization") or {}
                loc = item.get("jobLocation") or {}
                loc = loc[0] if isinstance(loc, list) and loc else loc
                addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
                return {"title": item.get("title"), "company": org.get("name") if isinstance(org, dict) else org,
                        "location": addr.get("addressLocality") if isinstance(addr, dict) else None,
                        "description": html_to_text(item.get("description")), "posted_at": item.get("datePosted"),
                        "url": url}
    micro = _microdata(page)  # schema.org microdata (e.g. SAP SuccessFactors career sites like adesso)
    if micro.get("description"):
        return {"title": micro.get("title") or _page_title(page), "company": micro.get("name") or _site_name(page),
                "location": micro.get("addressLocality"), "description": micro["description"],
                "posted_at": micro.get("datePosted"), "url": url}
    body = re.sub(r"(?is)<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>", " ", page)
    body = re.sub(r"(?is)<div[^>]+(?:cookie|consent|banner)[^>]*>.*?</div>", " ", body)
    return {"title": _page_title(page), "company": _site_name(page), "location": None,
            "description": html_to_text(body), "posted_at": None, "url": url}


def _page_title(page: str) -> str | None:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.DOTALL | re.IGNORECASE)
    if h1 and html_to_text(h1.group(1)):
        return html_to_text(h1.group(1))
    t = re.search(r"<title[^>]*>(.*?)</title>", page, re.DOTALL | re.IGNORECASE)
    return re.split(r"\s+[|–-]\s+", html_to_text(t.group(1)) or "")[0] or None if t else None


def _site_name(page: str) -> str | None:
    """og:site_name, else the last part of '<title>Job | Company</title>'."""
    m = re.search(r'<meta[^>]+property="og:site_name"[^>]+content="([^"]+)"', page, re.IGNORECASE)
    if m:
        return m.group(1)
    t = re.search(r"<title[^>]*>(.*?)</title>", page, re.DOTALL | re.IGNORECASE)
    parts = re.split(r"\s+\|\s+", html_to_text(t.group(1)) or "") if t else []
    return parts[-1].strip() if len(parts) > 1 and 2 <= len(parts[-1].strip()) <= 60 else None


class _Microdata(HTMLParser):
    """Collects the text of elements carrying itemprop=title/description/name/addressLocality/
    datePosted (first occurrence each; `content` attributes win)."""
    WANTED = {"title", "description", "name", "addressLocality", "datePosted"}
    VOID = {"br", "img", "meta", "link", "input", "hr", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: dict[str, str] = {}
        self._open: list[list] = []   # [prop, depth, chunks]
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        prop = a.get("itemprop")
        if tag in ("br", "p", "li", "div") and self._open:
            for o in self._open:
                o[2].append("\n• " if tag == "li" else "\n")
        if prop in self.WANTED and prop not in self.found:
            if a.get("content"):
                self.found[prop] = a["content"].strip()
            elif tag not in self.VOID:
                self._open.append([prop, self._depth, []])
        if tag not in self.VOID:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        self._depth -= 1
        while self._open and self._open[-1][1] >= self._depth:
            prop, _, chunks = self._open.pop()
            text = re.sub(r"[ \t]+", " ", "".join(chunks))
            text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
            if text:
                self.found.setdefault(prop, text)

    def handle_data(self, data):
        for o in self._open:
            o[2].append(data)


def _microdata(page: str) -> dict[str, str]:
    p = _Microdata()
    try:
        p.feed(page)
    except Exception:  # broken HTML: whatever was found so far
        pass
    return p.found


_SR_PATH = re.compile(r"^/([^/]+)/(\d{6,})")


def _smartrecruiters(url: str) -> dict | None:
    """jobs.smartrecruiters.com/<Company>/<id>-… → the public Posting API (no login, one GET).
    The job pages themselves carry no schema.org data, only a script-rendered page."""
    m = _SR_PATH.match(urlsplit(url).path)
    if not m:
        return None
    company, posting_id = m.groups()
    try:
        r = httpx.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}",
                      headers={"User-Agent": USER_AGENT}, timeout=30)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    d = r.json()
    sections = (d.get("jobAd") or {}).get("sections") or {}
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
        s = sections.get(key) or {}
        if s.get("text"):
            parts.append(f"{s.get('title') or ''}\n{html_to_text(s['text'])}".strip())
    loc = d.get("location") or {}
    remote = " (Remote)" if loc.get("remote") else ""
    return {"title": d.get("name"), "company": (d.get("company") or {}).get("name"),
            "location": (loc.get("city") or "") + remote or None, "description": "\n\n".join(parts) or None,
            "posted_at": (d.get("releasedDate") or "")[:10] or None,
            "url": d.get("postingUrl") or url, "apply_url": d.get("applyUrl")}


_APPLY_WORDS = re.compile(r"bewerb|apply|application|candidat|karriere|career", re.IGNORECASE)
_APPLY_STRONG = re.compile(r"bewerb|apply|application", re.IGNORECASE)
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"')\]]+")
_EMAIL_IN_TEXT = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_EMAIL_CONTEXT = re.compile(r"bewerb|unterlagen|lebenslauf|application|apply|cv\b|résumé|resume|send|senden|schick|richten",
                            re.IGNORECASE)
_NOT_APPLY_EMAIL = re.compile(r"^(no-?reply|noreply|datenschutz|privacy|dsb|webmaster|info@.*\.(?:png|jpg))", re.IGNORECASE)


def apply_target_from_text(text: str | None, posting_url: str | None = None) -> dict:
    """Where to apply, as stated in the posting text (user request 2026-10-18): a link next to
    "bewerben / apply / application", or an email address next to "Bewerbung / Unterlagen / send …".
    Returns {apply_url?, apply_email?}: both when the text names both (2026-10-22), {} if neither."""
    if not text:
        return {}
    posting = canonical_url(posting_url) if posting_url else None
    best = None
    for m in _URL_IN_TEXT.finditer(text):
        url = m.group(0).rstrip(".,;:")
        if posting and canonical_url(url) == posting:
            continue
        before = text[max(0, m.start() - 120):m.start()]
        score = 2 if _APPLY_STRONG.search(url) else 0
        score += 2 if _APPLY_STRONG.search(before) else (1 if _APPLY_WORDS.search(before + url) else 0)
        if score >= 2 and (best is None or score > best[0]):
            best = (score, url)
    found = {"apply_url": best[1]} if best else {}
    for m in _EMAIL_IN_TEXT.finditer(text):
        email = m.group(1).rstrip(".")
        around = text[max(0, m.start() - 160):m.end() + 40]
        if not _NOT_APPLY_EMAIL.match(email) and _EMAIL_CONTEXT.search(around):
            return found | {"apply_email": email}
    return found


class _Links(HTMLParser):
    """<a href> targets with their link text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[list[str]] = []
        self._in: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._in = [dict(attrs).get("href") or "", ""]
            self.links.append(self._in)

    def handle_endtag(self, tag):
        if tag == "a":
            self._in = None

    def handle_data(self, data):
        if self._in is not None:
            self._in[1] += data


def _apply_link_from_html(page: str, base_url: str) -> str | None:
    """The page's "Jetzt bewerben" / "Apply now" link (absolute), if it has one."""
    from urllib.parse import urljoin

    p = _Links()
    try:
        p.feed(page)
    except Exception:
        pass
    for href, label in p.links:
        href = href.strip()
        if not href or href.startswith(("#", "javascript:")):
            continue
        if href.startswith("mailto:"):
            continue
        if _APPLY_STRONG.search(label) and len(label.strip()) <= 60:
            url = urljoin(base_url, href)
            if re.match(r"https?://", url) and canonical_url(url) != canonical_url(base_url):
                return url
    return None


def _walk_ld(data):
    if isinstance(data, list):
        for x in data:
            yield from _walk_ld(x)
    elif isinstance(data, dict):
        yield data
        for x in data.get("@graph") or []:
            yield from _walk_ld(x)


def _salary_from_text(text: str) -> str | None:
    """A line of the posting that states a salary the §5a parser can read, if any."""
    for line in text.splitlines():
        if _SALARY_LINE.search(line) and re.search(r"\d", line) and checks.parse_annual_salary(line.strip()):
            return line.strip()[:200]
    return None


def _guess_title(text: str) -> str | None:
    for line in text.splitlines():
        s = line.strip()
        if 5 <= len(s) <= 140:
            return s
    return None


def _filter_for(conn: sqlite3.Connection, title: str) -> int | None:
    """The first active filter whose keywords match the title (for motivation and min_fit_score)."""
    for f in load_filters(conn, active_only=True):
        if keyword_match(title, f.keywords):
            return f.id
    return None


_EMAIL = re.compile(r"^(?:mailto:)?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})$")


def set_apply_target(conn: sqlite3.Connection, job_id: int, target: str | None) -> dict:
    """Where to apply (user request 2026-10-18): a link (an ATS form, the company's career page)
    or an email address. A link goes to jobs.apply_url; an email address to apply_email with
    apply_method 'email', so the writer stage saves an email draft. Empty clears the link."""
    jobs.get_job(conn, job_id)  # raises if unknown
    target = (target or "").strip()
    if not target:
        conn.execute("UPDATE jobs SET apply_url = NULL, updated_at = datetime('now') WHERE id = ?", (job_id,))
        conn.commit()
        return {"job_id": job_id, "apply_url": None}
    if m := _EMAIL.match(target):
        conn.execute("UPDATE jobs SET apply_email = ?, apply_method = 'email', updated_at = datetime('now') "
                     "WHERE id = ?", (m.group(1), job_id))
        conn.commit()
        return {"job_id": job_id, "apply_email": m.group(1)}
    if not re.match(r"https?://\S+$", target) or len(target) > 2000:
        raise ManualJobError("where to apply: give a link (http:// or https://) or an email address")
    conn.execute("UPDATE jobs SET apply_url = ?, updated_at = datetime('now') WHERE id = ?", (target, job_id))
    conn.commit()
    return {"job_id": job_id, "apply_url": target}


MAX_ADDRESS = 400


def set_apply_places(conn: sqlite3.Connection, job_id: int, url: str | None, email: str | None,
                     address: str | None) -> dict:
    """Where to apply, all at once (user request 2026-10-22): a posting may name a link, an email
    address and a postal address; each is kept. Empty clears that one. An email address sets
    apply_method 'email' (the writer stage then saves an email draft); clearing it falls back to
    'portal' when a link is left, else 'unknown'."""
    job = jobs.get_job(conn, job_id)  # raises if unknown
    url, email = (url or "").strip(), (email or "").strip()
    address = "\n".join(line.strip() for line in (address or "").strip().splitlines() if line.strip())
    if url and (not re.match(r"https?://\S+$", url) or len(url) > 2000):
        raise ManualJobError("where to apply: the link must start with http:// or https://")
    if email:
        m = _EMAIL.match(email)
        if not m:
            raise ManualJobError(f"where to apply: {email!r} is not an email address")
        email = m.group(1)
    if len(address) > MAX_ADDRESS:
        raise ManualJobError(f"where to apply: the postal address is longer than {MAX_ADDRESS} characters")
    method = job["apply_method"]
    if email:
        method = "email"
    elif method == "email":
        method = "portal" if url else "unknown"
    conn.execute("""UPDATE jobs SET apply_url = ?, apply_email = ?, apply_address = ?, apply_method = ?,
                    updated_at = datetime('now') WHERE id = ?""",
                 (url or None, email or None, address or None, method, job_id))
    conn.commit()
    return {"job_id": job_id, "apply_url": url or None, "apply_email": email or None,
            "apply_address": address or None, "apply_method": method}


def reevaluate(conn: sqlite3.Connection, job_id: int, changed_by: str = "user") -> dict:
    """Evaluate a job again with the posting text it already has (user request 2026-10-18): clears
    the fit score, notes and project ideas, then the single-job run scores it again.
    - skipped → 'new' (screened again), so the new evaluation can shortlist it;
    - any other status stays: the job is only re-scored (evaluate_job score-only), its documents
      and pipeline status are untouched. A documents request is kept."""
    job = jobs.get_job(conn, job_id)
    if job["status"] == "new" and job["fit_score"] is None:
        return {"job_id": job_id, "status": "new", "note": "not evaluated yet"}
    if job["status"] != "skipped":
        conn.execute("UPDATE jobs SET fit_score = NULL, fit_notes = NULL, project_suggestions = NULL, "
                     "updated_at = datetime('now') WHERE id = ?", (job_id,))
        conn.commit()
        return {"job_id": job_id, "status": job["status"], "note": "to be scored again (status stays)"}
    # The §5a checks run again, so a salary/work-authorization flag isn't lost by re-evaluating.
    p = JobPosting(source=job["source"], url=job["url"], title=job["title"], company=job["company"],
                   location=job["location"], description=job["description"], salary_text=job["salary_text"])
    note = _screen(p, float(get_settings(conn).get("blue_card_salary_min", "45934.20")))
    resolved = conn.execute("SELECT 1 FROM status_history WHERE job_id = ? AND from_status = 'needs_attention' "
                            "AND changed_by = 'user'", (job_id,)).fetchone()
    if resolved and p.status == "needs_attention":  # the user already dealt with that flag
        p.status, p.attention_reason, note = "new", None, None
    conn.execute("UPDATE jobs SET fit_score = NULL, fit_notes = NULL, project_suggestions = NULL, "
                 "salary_annual_eur = ?, salary_flag = ?, updated_at = datetime('now') WHERE id = ?",
                 (p.salary_annual_eur, p.salary_flag, job_id))
    jobs.set_status(conn, job_id, p.status, changed_by, attention_reason=p.attention_reason,
                    note="re-evaluation requested" + (f"; {note}" if note else ""))
    conn.commit()
    return {"job_id": job_id, "status": p.status, "note": note or "to be evaluated again"}


CLOSED = ("applied", "feedback", "interview", "offer", "rejected", "withdrawn")


def add_manual_job(conn: sqlite3.Connection, url: str, text: str | None = None, title: str | None = None,
                   company: str | None = None, location: str | None = None, apply_to: str | None = None) -> dict:
    """Add a job from a link (fetched if public) and/or pasted text, and optionally where to apply
    (a link or email address, see set_apply_target). If the job is already known (R8), the pasted
    text and apply target are added to it instead. Returns {job_id, created, status, note}."""
    url = (url or "").strip()
    if not re.match(r"https?://", url):
        raise ManualJobError("give the job's link (http:// or https://)")
    if apply_to and apply_to.strip() and not (_EMAIL.match(apply_to.strip()) or re.match(r"https?://\S+$", apply_to.strip())):
        raise ManualJobError("where to apply: give a link (http:// or https://) or an email address")
    result = _add_manual_job(conn, url, text, title, company, location)
    if apply_to and apply_to.strip():
        set_apply_target(conn, result["job_id"], apply_to)
    return result


def _add_manual_job(conn: sqlite3.Connection, url: str, text: str | None, title: str | None,
                    company: str | None, location: str | None) -> dict:
    text = (text or "").strip()[:MAX_TEXT] or None
    # a job removed by the automatic clean-up may be added again by hand (its tombstone goes below)
    row = jobs.find_seen(conn, canonical_url(url), include_deleted=False)
    seen = {"seen": True, "job_id": row["id"], "status": row["status"]} if row else {"seen": False}
    if seen["seen"]:
        if text:
            update_posting(conn, seen["job_id"], text)
            return {"job_id": seen["job_id"], "created": False, "status": jobs.get_job(conn, seen["job_id"])["status"],
                    "note": "already known — the pasted posting was added to it"}
        return {"job_id": seen["job_id"], "created": False, "status": seen["status"], "note": "already known"}

    fetched: dict = {}
    if not text:
        fetched = fetch_posting(url)
        text = (fetched.get("description") or "")[:MAX_TEXT] or None
    title = (title or fetched.get("title") or (_guess_title(text) if text else None) or "").strip()
    if not title:
        raise ManualJobError("couldn't find a job title — add the title or paste the posting")
    p = JobPosting(source="manual", url=fetched.get("url") or url, title=title[:200],
                   company=(company or fetched.get("company") or None), location=(location or fetched.get("location") or None),
                   description=text, posted_at=(fetched.get("posted_at") or None),
                   salary_text=_salary_from_text(text) if text else None)
    p.source_job_id = canonical_url(url)
    p.canonical_url = canonical_url(p.url)
    p.fingerprint = fingerprint(p.company, p.title, p.location, p.canonical_url)
    dup = jobs.find_seen(conn, p.canonical_url, p.fingerprint, include_deleted=False)
    conn.execute("DELETE FROM deleted_jobs WHERE canonical_url IN (?, ?) OR fingerprint = ?",
                 (p.canonical_url, p.source_job_id, p.fingerprint))
    if dup:
        return {"job_id": dup["id"], "created": False, "status": dup["status"], "note": "already known (same job)"}
    p.filter_id = _filter_for(conn, p.title)
    threshold = float(get_settings(conn).get("blue_card_salary_min", "45934.20"))
    note = _screen(p, threshold)
    p.id = jobs.insert_job(conn, p, note=("added manually" + (f"; {note}" if note else "")))
    conn.commit()
    _auto_apply_target(conn, p.id, text, p.url, fetched.get("apply_url"))
    return {"job_id": p.id, "created": True, "status": p.status, "note": note or "added"}


def _auto_apply_target(conn: sqlite3.Connection, job_id: int, text: str | None, posting_url: str,
                       page_link: str | None = None) -> dict:
    """Fill in the apply link and/or email the job doesn't have yet: the page's "Apply" link, else the
    link the posting text names, and the email address the text names. Never overwrites what the
    user (or the evaluation) already set."""
    job = jobs.get_job(conn, job_id)
    found = apply_target_from_text(text, posting_url)
    if page_link:
        found["apply_url"] = page_link
    found = {k: v for k, v in found.items() if not job.get(k)}
    for value in found.values():
        set_apply_target(conn, job_id, value)
    return found


def update_posting(conn: sqlite3.Connection, job_id: int, text: str, changed_by: str = "user") -> dict:
    """The user adds/replaces the full posting text. The job is screened again and set back to
    'new', so the next (or a single-job) run evaluates it with the full text."""
    text = (text or "").strip()[:MAX_TEXT]
    if len(text) < 80:
        raise ManualJobError("paste the full posting (at least a few sentences)")
    job = jobs.get_job(conn, job_id)
    if job["status"] in CLOSED:
        raise ManualJobError(f"job {job_id} is already {job['status']}; its evaluation isn't redone")
    p = JobPosting(source=job["source"], url=job["url"], title=job["title"], company=job["company"],
                   location=job["location"], description=text,
                   salary_text=job["salary_text"] or _salary_from_text(text))
    threshold = float(get_settings(conn).get("blue_card_salary_min", "45934.20"))
    note = _screen(p, threshold)
    conn.execute(
        """UPDATE jobs SET description = ?, salary_text = ?, salary_annual_eur = ?, salary_flag = ?,
                  fit_score = NULL, fit_notes = NULL, project_suggestions = NULL, updated_at = datetime('now')
           WHERE id = ?""", (text, p.salary_text, p.salary_annual_eur, p.salary_flag, job_id))
    to = p.status  # 'new', or 'needs_attention' if the full text trips a §5a check
    jobs.set_status(conn, job_id, to, changed_by, attention_reason=p.attention_reason,
                    note="full posting added" + (f"; {note}" if note else "") + " — to be evaluated again")
    conn.commit()
    found = _auto_apply_target(conn, job_id, text, job["url"])
    return {"job_id": job_id, "status": to, "note": note} | found
