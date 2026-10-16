"""Job-alert emails (LinkedIn, StepStone, XING) as a source — CLAUDE.md §5b, Phase 9.

Strictly read-only on the mailbox: the ALERTS account (falls back to SEND credentials), folder
opened with EXAMINE (select readonly), messages fetched with BODY.PEEK — no flag changes, nothing
marked as seen, never STORE/COPY/MOVE/EXPUNGE/APPEND. No LinkedIn login, no cookies, no use of the
user's board accounts: LinkedIn job IDs are taken from the alert links themselves (no request to
linkedin.com). StepStone/XING tracking links are resolved with anonymous, throttled GETs (R6).

Selection is by sender + SINCE <last successful read> (first run: 14 days); processed Message-IDs
are stored in alert_messages so a message is parsed once. Emails are parsed once per process; each
filter then keeps the postings whose title matches its keywords (jobs matching no filter are not
stored — user decision).
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from email import policy
from email.message import EmailMessage
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

from core import db, mail_config, mail_drafts
from core.dedup import canonical_url
from core.models import JobPosting, SearchFilter
from core.sources.base import MIN_INTERVAL_S, USER_AGENT, SourceError, Throttle, html_to_text, keyword_match, register

FIRST_RUN_DAYS = 14
CACHE_TTL_S = 900
MAX_RESOLVES_PER_RUN = 40
MAX_ATTEMPTS = 3
_LINKEDIN_JOB = re.compile(r"https?://[\w.-]*linkedin\.com/(?:comm/)?jobs/view/(?:[^/?\s]*?-)?(\d{6,})[^\s\"'<>]*")
_NOISE = re.compile(
    r"^(?:\d+\s+(?:school|company)\s+alum(?:ni|nus)?|\d+\s+connections?|this company is actively hiring|be an early applicant|"
    r"promoted|easy apply|actively recruiting|view job:?|view|apply|apply now|apply with .{0,40}|new|\d+\s+applicants?|"
    r"[€$£]\s?\d.*|\d.*[€$£].*|-{3,}|={3,})$", re.IGNORECASE)
_WORK_MODE = re.compile(r"\((remote|hybrid|on-site|onsite)\)", re.IGNORECASE)


@dataclass
class AlertJob:
    board: str
    url: str                     # job URL (LinkedIn: from the link; StepStone/XING: after resolving)
    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: str | None = None
    description: str | None = None
    received: str | None = None  # ISO date of the email
    salary_text: str | None = None


# ── parsing (pure functions, unit-tested with fixtures) ─────────────────────

def _lines_before(text: str, pos: int) -> list[str]:
    """Non-empty lines above a 'View job: URL' line, up to the previous block separator."""
    above = text[:pos].splitlines()
    out: list[str] = []
    for line in reversed(above):
        s = line.strip()
        if not s:
            if out:
                # a blank line inside a block is fine; two consecutive blanks end it
                continue
            continue
        if re.fullmatch(r"-{5,}|={5,}", s) or s.lower().startswith(("see all jobs", "view all jobs")) or s.startswith("http"):
            break
        out.append(s)
        if len(out) >= 6:
            break
    return list(reversed(out))


def parse_linkedin(msg: EmailMessage) -> list[AlertJob]:
    """LinkedIn alert/recommendation emails: every /jobs/view/<id> link with title/company/location
    from the plain-text block above it (falls back to the HTML link text)."""
    received = _received(msg)
    jobs: dict[str, AlertJob] = {}
    text_part = msg.get_body(("plain",))
    if text_part:
        text = text_part.get_content()
        for m in _LINKEDIN_JOB.finditer(text):
            job_id = m.group(1)
            if job_id in jobs:
                continue
            line_start = text.rfind("\n", 0, m.start()) + 1
            block = [s for s in _lines_before(text, line_start) if not _NOISE.match(s)]
            title, company, location = _split_block(block)
            jobs[job_id] = AlertJob("linkedin", f"https://www.linkedin.com/jobs/view/{job_id}", title, company,
                                    location, _work_mode(company, location), received=received)
    html_part = msg.get_body(("html",))
    if html_part:
        for href, text in _links(html_part.get_content()):
            m = _LINKEDIN_JOB.match(href)
            if not m or not text:
                continue
            job = jobs.setdefault(m.group(1), AlertJob("linkedin", f"https://www.linkedin.com/jobs/view/{m.group(1)}",
                                                       received=received))
            if not job.title and text.lower() not in ("view", "view job", "apply"):
                job.title = text.split(" · ")[0].strip()
    return [j for j in jobs.values() if j.title]


def _split_block(block: list[str]) -> tuple[str | None, str | None, str | None]:
    """[title, company, location] or [title, 'Company · Location (Mode)'] (+ ignored extras)."""
    if not block:
        return None, None, None
    for i, line in enumerate(block):
        if " · " in line and i > 0:
            company, _, location = line.partition(" · ")
            return block[i - 1], company.strip(), location.strip()
    # heading lines ("Embedded jobs", "Recommendations …") can precede the title; take the last 3
    tail = block[-3:]
    if len(tail) == 3:
        return tail[0], tail[1], tail[2]
    if len(tail) == 2:
        return tail[0], tail[1], None
    return tail[0], None, None


def _work_mode(*parts: str | None) -> str | None:
    for p in parts:
        if p and (m := _WORK_MODE.search(p)):
            return {"on-site": "onsite"}.get(m.group(1).lower(), m.group(1).lower())
    return None


_INSTAFFO_LINK = re.compile(r"\[([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]\((https://app\.instaffo\.com/candidate/job/"
                            r"([0-9a-f-]{36})[^)\s]*)\)")
_INSTAFFO_BADGE = re.compile(r"top[- ]?(?:skill[- ])?match|top gehalt|remote|jetzt .*ansehen|company logo|^\W*$",
                             re.IGNORECASE)
# Card fields, in the current German labels and the older English ones (2025 mails).
_INSTAFFO_FIELDS = {"logo": "company", "company-name": "company", "ort": "city", "location": "city",
                    "skills": "skills", "gehalt": "salary", "salary": "salary", "remote": "modes",
                    "work-mode": "modes", "arbeitsmodell": "modes"}
_INSTAFFO_FIELD = re.compile(r"^\s*\[([A-Za-z-]+)\]\s*(.*?)\s*$")


def parse_instaffo(msg: EmailMessage) -> list[AlertJob]:
    """Instaffo job-suggestion mails (user request 2026-10-16). Everything comes from the mail text:
    Instaffo links carry an SSO login token, so they are NEVER opened (R2) and the token is never
    stored (the job URL is rebuilt from the job's UUID). Mails without suggestion cards (profile
    reminders, salary questions, application updates) yield no jobs."""
    part = msg.get_body(("plain",))
    if not part:
        return []
    text = part.get_content()
    received = _received(msg)
    cards: dict[str, dict] = {}
    for line in text.splitlines():
        links = list(_INSTAFFO_LINK.finditer(line))
        uuid = links[0].group(3) if links else (next(reversed(cards)) if cards else None)
        if uuid is None:
            continue
        card = cards.setdefault(uuid, {"title": None, "company": None, "city": None, "skills": None,
                                       "salary": None, "modes": None})
        # fragments: every link label, plus the text outside the links ("[Ort] Darmstadt")
        fragments = [" ".join(m.group(1).split()) for m in links]
        outside = _INSTAFFO_LINK.sub("\t", line)
        fragments += [s.strip() for s in outside.split("\t") if s.strip()]
        for frag in fragments:
            field = _INSTAFFO_FIELD.match(frag)
            if field and field.group(1).lower() in _INSTAFFO_FIELDS:
                card[_INSTAFFO_FIELDS[field.group(1).lower()]] = field.group(2) or None
            elif links and frag in fragments[:len(links)] and not card["title"] \
                    and not _INSTAFFO_BADGE.search(frag) and not frag.startswith("["):
                card["title"] = frag
    jobs = []
    for uuid, c in cards.items():
        if not (c["title"] and c["skills"] is not None and c["city"]):
            continue  # not a suggestion card (e.g. a link in an application update)
        salary = c["salary"] if c["salary"] and re.search(r"\d", c["salary"]) else None
        details = [f"Skills: {c['skills']}" if c["skills"] else None,
                   f"Gehalt: {salary}" if salary else None,
                   f"Arbeitsmodell: {c['modes']}" if c["modes"] else None,
                   "(From an Instaffo job-suggestion email; the full ad is only visible after login on Instaffo.)"]
        jobs.append(AlertJob("instaffo", f"https://app.instaffo.com/candidate/job/{uuid}", c["title"].rstrip("…").strip(),
                             c["company"], c["city"], _instaffo_mode(c["modes"]),
                             description="\n".join(x for x in details if x), received=received))
        jobs[-1].salary_text = salary
    return jobs


def _instaffo_mode(modes: str | None) -> str | None:
    m = {x.strip().lower() for x in (modes or "").split(",") if x.strip()}
    if m == {"remote"}:
        return "remote"
    if "hybrid" in m or len(m) > 1:
        return "hybrid"
    if m & {"on-site", "onsite", "vor ort"}:
        return "onsite"
    return None


def parse_board_links(msg: EmailMessage, board: str) -> list[AlertJob]:
    """StepStone / XING: candidate job links (tracking redirects) with their link text. Resolved later.
    NOTE: not yet verified against a real StepStone/XING alert (none in the inbox as of 2026-10-15)."""
    html_part = msg.get_body(("html",))
    if not html_part:
        return []
    received = _received(msg)
    out: dict[str, AlertJob] = {}
    for href, text in _links(html_part.get_content()):
        host = (urlsplit(href).hostname or "").lower()
        if board not in host or not text or len(text) < 6:
            continue
        if re.search(r"unsubscribe|abmelden|settings|einstellungen|privacy|datenschutz|impressum|login|app\b",
                     href + " " + text, re.IGNORECASE):
            continue
        out.setdefault(href, AlertJob(board, href, text, received=received))
    return list(out.values())


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None


def _links(html: str) -> list[tuple[str, str]]:
    p = _LinkParser()
    p.feed(html)
    return p.links


def _received(msg: EmailMessage) -> str | None:
    try:
        return email.utils.parsedate_to_datetime(msg["Date"]).date().isoformat()
    except (TypeError, ValueError):
        return None


# ── IMAP (read-only) ────────────────────────────────────────────────────────

def _or_from(addresses: list[str]) -> list[str]:
    """IMAP search criteria: OR FROM a OR FROM b FROM c."""
    if len(addresses) == 1:
        return ["FROM", f'"{addresses[0]}"']
    return ["OR", "FROM", f'"{addresses[0]}"', *_or_from(addresses[1:])]


@dataclass
class _Fetched:
    message_id: str
    board: str
    msg: EmailMessage


def read_new_messages(conn, settings: dict[str, str], cfg=None) -> list[_Fetched]:
    """EXAMINE the alert folder, find alert mails by sender since the last successful read, skip
    Message-IDs already processed, and return the new ones (BODY.PEEK only)."""
    senders = json.loads(settings.get("alert_senders") or "[]")
    by_addr = {s["from"].lower(): s["board"] for s in senders if s.get("from") and s.get("board")}
    if not by_addr:
        return []
    last = settings.get("email_alerts_last_success") or ""
    since_day = date.fromisoformat(last) if last else date.today() - timedelta(days=FIRST_RUN_DAYS)
    since = since_day.strftime("%d-%b-%Y")
    folder = settings.get("alert_folder") or "INBOX"

    cfg = cfg or mail_config.load_alerts_config()
    imap = mail_drafts.connect(cfg)
    try:
        typ, data = imap.select(mail_drafts._quote(folder), readonly=True)  # = EXAMINE
        if typ != "OK":
            raise SourceError(f"email_alerts: folder {folder!r} not found ({data})")
        typ, data = imap.uid("SEARCH", None, "SINCE", since, *_or_from(list(by_addr)))
        if typ != "OK":
            raise SourceError(f"email_alerts: IMAP search failed ({data})")
        uids = data[0].split() if data and data[0] else []
        done = {r[0] for r in conn.execute("SELECT message_id FROM alert_messages WHERE status IN ('processed', 'failed')")}
        out: list[_Fetched] = []
        for uid in uids:
            typ, head = imap.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM)])")
            if typ != "OK" or not head or not isinstance(head[0], tuple):
                continue
            h = email.message_from_bytes(head[0][1])
            mid = (h["Message-ID"] or f"<uid-{uid.decode()}@{folder}>").strip()
            sender = email.utils.parseaddr(h["From"] or "")[1].lower()
            if mid in done or sender not in by_addr:
                continue
            typ, body = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not body or not isinstance(body[0], tuple):
                continue
            out.append(_Fetched(mid, by_addr[sender], email.message_from_bytes(body[0][1], policy=policy.default)))
        return out
    finally:
        try:
            imap.logout()
        except imaplib.IMAP4.error:
            pass


# ── resolving StepStone/XING tracking links (anonymous, throttled, R6) ──────

class _Resolver:
    def __init__(self):
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
        self.throttles: dict[str, Throttle] = {}
        self.count = 0
        self.blocked = False

    def resolve(self, job: AlertJob) -> AlertJob | None:
        if self.blocked or self.count >= MAX_RESOLVES_PER_RUN:
            raise SourceError("resolve budget used up or blocked for this run")
        host = urlsplit(job.url).hostname or ""
        self.throttles.setdefault(host, Throttle(MIN_INTERVAL_S)).wait()
        self.count += 1
        try:
            r = self.client.get(job.url)
        except httpx.HTTPError as e:
            raise SourceError(f"{job.board}: network error resolving a link: {type(e).__name__}") from None
        finally:
            self.client.cookies.clear()  # no cookies kept between requests
        if r.status_code in (403, 429):
            self.blocked = True
            raise SourceError(f"{job.board}: HTTP {r.status_code} while resolving links (stopped for this run)")
        final = str(r.url)
        if canonical_url(final) == canonical_url(job.url) or not re.search(r"stellenangebote|/jobs?/", final):
            return None  # not a job page (newsletter, profile, search page …)
        job.url = final
        job.description = _jsonld_description(r.text)
        return job


def _jsonld_description(page: str) -> str | None:
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting" and item.get("description"):
                return html_to_text(item["description"])
    return None


# ── the adapter ─────────────────────────────────────────────────────────────

@register
class EmailAlerts:
    key = "email_alerts"

    def __init__(self):
        self.last_errors: list[dict] = []
        self._cache: tuple[float, list[AlertJob]] | None = None
        self.dry_run = False  # set by run_search: read and parse, but record nothing

    def search(self, f: SearchFilter, limit: int) -> list[JobPosting]:
        """Every alert job whose title matches the filter. `limit` is ignored: it protects scraped
        websites (R6), but these are the user's own mails, already read — capping them lost jobs,
        because a processed mail is never read again (fixed 2026-10-18)."""
        self.last_errors = []
        jobs = self._all_jobs()
        cutoff = (date.today() - timedelta(days=f.max_age_days)).isoformat()
        out = []
        for j in jobs:
            if not j.title or not keyword_match(j.title, f.keywords):
                continue  # matches no keyword of this filter (other filters may still take it)
            if j.received and j.received < cutoff:
                continue
            out.append(self._posting(j))
        return out

    def _posting(self, j: AlertJob) -> JobPosting:
        return JobPosting(
            source=self.key, source_job_id=f"{j.board}:{canonical_url(j.url)}", url=j.url, title=j.title,
            company=j.company, location=j.location, work_mode=j.work_mode, description=j.description,
            posted_at=j.received, salary_text=j.salary_text,
        )

    def _store_unmatched(self, conn, jobs: list[AlertJob]) -> None:
        """Jobs no active filter's keywords match are kept for the user to review (needs_attention /
        alert_review) instead of being dropped (user request 2026-10-18)."""
        from core.filters import load_filters
        from core.search import store_for_review

        filters = load_filters(conn, active_only=True)
        if not filters:
            return
        cutoff = (date.today() - timedelta(days=max(f.max_age_days for f in filters))).isoformat()
        unmatched = [j for j in jobs if j.title and not (j.received and j.received < cutoff)
                     and not any(keyword_match(j.title, f.keywords) for f in filters)]
        if unmatched:
            store_for_review(conn, [self._posting(j) for j in unmatched])

    def fetch_details(self, job: JobPosting) -> JobPosting:
        return job  # no extra request (LinkedIn: never; StepStone/XING: described while resolving)

    # Parse all new alert mails once per process (all filters of a run share it).
    def _all_jobs(self) -> list[AlertJob]:
        if self._cache and time.monotonic() - self._cache[0] < CACHE_TTL_S:
            return self._cache[1]
        conn = db.connect()
        try:
            settings = db.get_settings(conn)
            try:
                fetched = read_new_messages(conn, settings)
            except (RuntimeError, imaplib.IMAP4.error, OSError) as e:
                raise SourceError(f"email_alerts: {e}") from None
            resolver = _Resolver()
            jobs: list[AlertJob] = []
            had_error = False
            for f in fetched:
                try:
                    found = self._parse(f, resolver)
                except SourceError as e:
                    had_error = True
                    self.last_errors.append({"source": self.key, "message": str(e)})
                    self._record_failure(conn, f)
                    continue
                jobs.extend(found)
                conn.execute(
                    """INSERT INTO alert_messages (message_id, board, received_at, jobs_found, status)
                       VALUES (?, ?, ?, ?, 'processed')
                       ON CONFLICT(message_id) DO UPDATE SET status = 'processed', jobs_found = excluded.jobs_found,
                         processed_at = datetime('now')""",
                    (f.message_id, f.board, _received(f.msg), len(found)))
            if not had_error:
                conn.execute("INSERT INTO settings (key, value) VALUES ('email_alerts_last_success', ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (date.today().isoformat(),))
            # the same job can arrive in several mails
            unique = {canonical_url(j.url): j for j in jobs}
            jobs_list = list(unique.values())
            if self.dry_run:
                conn.rollback()  # a dry run records nothing: the mails stay "new" for the real run
            else:
                self._store_unmatched(conn, jobs_list)  # commits, together with the processed mails
                conn.commit()
        finally:
            conn.close()
        if not self.dry_run:
            self._cache = (time.monotonic(), jobs_list)
        return jobs_list

    @staticmethod
    def _parse(f: _Fetched, resolver: _Resolver) -> list[AlertJob]:
        if f.board == "linkedin":
            return parse_linkedin(f.msg)
        if f.board == "instaffo":
            return parse_instaffo(f.msg)  # never resolves links (SSO tokens)
        resolved = []
        for cand in parse_board_links(f.msg, f.board):
            job = resolver.resolve(cand)  # raises SourceError → the message is retried next run
            if job:
                resolved.append(job)
        return resolved

    @staticmethod
    def _record_failure(conn, f: _Fetched) -> None:
        row = conn.execute("SELECT attempts FROM alert_messages WHERE message_id = ?", (f.message_id,)).fetchone()
        attempts = (row[0] if row else 0) + 1
        status = "failed" if attempts >= MAX_ATTEMPTS else "retry"
        conn.execute(
            """INSERT INTO alert_messages (message_id, board, received_at, status, attempts) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(message_id) DO UPDATE SET status = excluded.status, attempts = excluded.attempts,
                 processed_at = datetime('now')""",
            (f.message_id, f.board, _received(f.msg), status, attempts))
