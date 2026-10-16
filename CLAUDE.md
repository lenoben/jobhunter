# JobHunter — Project Blueprint

A local, open-source job-search assistant for the German market, driven by Claude Code on a
Claude Pro subscription (no Anthropic API key). It finds jobs, filters and scores them, writes a
tailored CV + cover letter per job, logs everything in SQLite, notifies via Telegram, and shows
everything in a localhost web UI. **Applying is always finished by the human.**

> This file is the source of truth. Read it fully at the start of every session.
> Build in the phases listed at the bottom. Do not skip ahead. After each phase, run its
> acceptance checks and stop for review.

---

## 1. Hard rules (never break these)

| # | Rule |
|---|------|
| R1 | **Never submit an application**, never click a final "Submit/Absenden/Bewerben" button, never send an email. Prepare everything; the user submits. |
| R2 | **Never type, store, or ask for passwords.** Never create accounts. Never attempt CAPTCHAs. Flag the job `needs_attention` with the reason instead. |
| R3 | **Secrets live only in `.env`** (gitignored): Telegram token, mail app passwords (SEND and ALERTS accounts). Never write them to SQLite, logs, generated files, or the UI. |
| R4 | **Personal data stays local.** `profile/` and `data/` are gitignored. Never send profile data anywhere except into Claude's own context and the generated documents. |
| R5  | **Never invent facts.** CVs and cover letters use only what is in `profile/profile.yaml`, plus inferred facts approved under R9. Anything else goes into the fit notes as a gap, never into the documents. |
| R6 | **Respect sources.** Prefer official/public APIs. Throttle scrapers (≥3 s between requests per site), cap results per run, and back off on 429/403. If a source blocks, record the error and continue with the others. |
| R7 | **Never use `ANTHROPIC_API_KEY`.** Everything runs on the Pro subscription. `run.ps1` must unset it before calling `claude`. |
| R8 | **Never process a job twice.** Always call `is_seen` before doing any work on a job. |
| R9  | **Inferred facts (approval required).** If a job needs something the profile lacks, but the profile clearly implies the ability (e.g. strong C/C++ → can learn a specific embedded toolchain), you may add it as an *inferred fact* only if: (a) it is a capability or learning statement ("kann mich schnell in X einarbeiten", "Grundlagen in X durch Y"), never claimed experience, years, employers, grades, or certificates; (b) it is recorded under `inferred` with statement, where, and basis; (c) the job is set to `needs_attention` (reason `inferred_facts`) and no email draft is created until the user approves. Rejected inferences are never reused. |
| R10 | **Relevance over completeness.** A cover letter mentions at most 2–3 projects or experiences, chosen by relevance to the job's requirements, and each must be linked to a specific requirement. Unrelated projects are left out even if impressive. The CV may list more, ordered by relevance. |
| R11 | **Project suggestions go to fit notes only.** For each gap, suggest 1–3 small, realistic projects the user could build (scope, estimated days, what requirement it covers). Never mention them in documents until the user adds the finished project to `profile.yaml`. |

---

## 2. Stack

| Part | Choice | Notes |
|------|--------|-------|
| Core + MCP server | **Python 3.12**, managed with **uv** | `mcp` package ≥ 2 (`MCPServer` from `mcp.server.mcpserver`; it was called `FastMCP` before 2.0) |
| Job sources | `httpx` for APIs, `python-jobspy` for scraped boards | Adapter pattern (see §5) |
| Database | **SQLite**, WAL mode, `foreign_keys=ON` | Single file `data/jobhunter.db` |
| Migrations | Plain numbered SQL files in `core/migrations/`, applied by `core/db.py` | Python owns the schema |
| Documents | **Typst** templates → PDF via the `typst` Python package | No LaTeX install needed |
| Web UI | **SvelteKit** (Node LTS) + `better-sqlite3` | Reads/writes the same DB file |
| Notifications | Telegram Bot API over HTTPS | One-way in v1 |
| Mail accounts | Generic IMAP over SSL, app passwords only, loaded by `core/mail_config.py` | Two accounts. **SEND** (`SEND_MAIL_ADDRESS`, `SEND_MAIL_APP_PASSWORD`, `SEND_IMAP_HOST`, `SEND_IMAP_PORT`; default **Yahoo** `imap.mail.yahoo.com:993`): `mail_drafts.py` saves application drafts there, never SMTP send in v1. **ALERTS** (`ALERTS_MAIL_ADDRESS`, `ALERTS_MAIL_APP_PASSWORD`, `ALERTS_IMAP_HOST`, `ALERTS_IMAP_PORT`; any provider, host required): read-only, used only by the `email_alerts` source (§5b). If the ALERTS address or password is empty, alerts are read with the SEND credentials. A config loaded for the alerts role can never create drafts or send, even when it falls back to SEND. Drafts folder: the folder with the IMAP `\Drafts` special-use flag; if none has it, fall back to a folder named `Draft` or `Drafts` (Yahoo uses `Draft`) |
| Scheduling | Windows Task Scheduler → `run.ps1` → `claude -p` | §9 |

---

## 3. Folder structure

```
jobhunter/
├─ CLAUDE.md                     ← this file
├─ README.md                     ← human setup guide (write in Phase 1, keep updated)
├─ .env.example                  ← committed; .env is gitignored
├─ .gitignore                    ← data/, profile/, output/, .env, node_modules, .venv
├─ .mcp.json                     ← registers the local MCP server for Claude Code
├─ .claude/
│  ├─ settings.json              ← permission allow-list for headless runs
│  └─ skills/
│     ├─ job-hunt/SKILL.md       ← the scheduled workflow (Phase 5)
│     └─ apply-assist/SKILL.md   ← interactive apply helper (Phase 8)
├─ pyproject.toml
├─ core/
│  ├─ db.py                      ← connection, WAL, migrations runner
│  ├─ migrations/001_init.sql
│  ├─ models.py                  ← dataclasses: JobPosting, SearchFilter, Application …
│  ├─ dedup.py                   ← URL canonicalisation + fingerprint
│  ├─ filters.py                 ← load active filters from DB
│  ├─ profile.py                 ← load + validate profile.yaml
│  ├─ docs.py                    ← render Typst → PDF
│  ├─ notify.py                  ← Telegram
│  ├─ checks.py                  ← screening: salary vs Blue Card, work-authorization keywords (§5a)
│  ├─ mail_config.py             ← SEND + ALERTS mail accounts from .env
│  ├─ mail_drafts.py             ← IMAP draft creation, SEND account only (Yahoo default)
│  └─ sources/
│     ├─ base.py                 ← Source protocol + registry
│     ├─ ba_jobsuche.py          ← Bundesagentur für Arbeit
│     ├─ arbeitnow.py
│     ├─ jobspy_source.py        ← Indeed DE, LinkedIn, Glassdoor
│     └─ email_alerts.py         ← LinkedIn/StepStone/XING job-alert emails, read-only (Phase 9)
├─ mcp_server/server.py          ← MCP tools (§6, mcp `MCPServer`)
├─ cli.py                        ← dev/testing commands (§11)
├─ templates/
│  ├─ cv_de.typ  cv_en.typ
│  ├─ letter_de.typ  letter_en.typ   ← DIN 5008 layout for DE
│  ├─ lib/                       ← shared layout (common.typ, cv.typ, letter.typ)
│  └─ examples/                  ← example content JSON = the content schema (render-test)
├─ profile/                      ← gitignored
│  ├─ profile.example.yaml       ← committed copy lives at repo root as profile.example.yaml
│  ├─ profile.yaml               ← user fills this in
│  └─ photo.jpg                  ← optional
├─ output/<job_id>/              ← gitignored: cv.pdf, anschreiben.pdf, notes.md
├─ data/jobhunter.db             ← gitignored
├─ logs/                         ← gitignored, one log file per run
├─ ui/                           ← SvelteKit app
├─ run.ps1                       ← entry point for Task Scheduler
└─ setup-task.ps1                ← registers the scheduled task
```

---

## 4. Database schema (`core/migrations/001_init.sql`)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE search_filters (
  id               INTEGER PRIMARY KEY,
  name             TEXT NOT NULL,
  active           INTEGER NOT NULL DEFAULT 1,
  keywords         TEXT NOT NULL,          -- JSON array, e.g. ["Backend Developer","Python"]
  exclude_keywords TEXT NOT NULL DEFAULT '[]',
  location         TEXT,                   -- e.g. "Mannheim"; NULL = Germany-wide
  radius_km        INTEGER DEFAULT 50,
  work_modes       TEXT NOT NULL DEFAULT '["remote","hybrid","onsite"]',
  employment_types TEXT NOT NULL DEFAULT '["full_time"]',  -- full_time | part_time | minijob | working_student | internship
  exclude_freelance INTEGER NOT NULL DEFAULT 1,
  languages        TEXT NOT NULL DEFAULT '["de","en"]',
  sources          TEXT NOT NULL DEFAULT '["ba_jobsuche","arbeitnow","jobspy"]',
  max_age_days     INTEGER NOT NULL DEFAULT 7,
  min_fit_score    INTEGER NOT NULL DEFAULT 60,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE jobs (
  id               INTEGER PRIMARY KEY,
  source           TEXT NOT NULL,          -- adapter key
  source_job_id    TEXT,                   -- board's own id if available
  url              TEXT NOT NULL,          -- original URL
  canonical_url    TEXT NOT NULL UNIQUE,   -- dedup key 1
  fingerprint      TEXT NOT NULL,          -- dedup key 2 (company|title|city)
  title            TEXT NOT NULL,
  company          TEXT,
  location         TEXT,
  work_mode        TEXT,                   -- remote | hybrid | onsite | unknown (Claude classifies)
  employment_type  TEXT,
  language         TEXT,                   -- de | en (posting language)
  salary_text      TEXT,
  posted_at        TEXT,
  description      TEXT,
  apply_method     TEXT,                   -- portal | email | external_ats | unknown
  apply_email      TEXT,
  fit_score        INTEGER,                -- 0–100, set by Claude
  fit_notes        TEXT,                   -- why it fits / gaps (Markdown)
  status           TEXT NOT NULL DEFAULT 'new',
  attention_reason TEXT,                   -- set when status = needs_attention
  filter_id        INTEGER REFERENCES search_filters(id),
  first_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX idx_jobs_status ON jobs(status);

CREATE TABLE applications (
  id               INTEGER PRIMARY KEY,
  job_id           INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
  cv_path          TEXT,
  letter_path      TEXT,
  doc_language     TEXT,                   -- de | en
  summary          TEXT,                   -- what was emphasised and why
  interview_prep   TEXT,                   -- expected questions, topics to revise (Markdown)
  method           TEXT,                   -- how it was / will be submitted
  email_draft_saved INTEGER NOT NULL DEFAULT 0,
  applied_at       TEXT,                   -- set by the USER via UI
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE status_history (
  id         INTEGER PRIMARY KEY,
  job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  from_status TEXT,
  to_status  TEXT NOT NULL,
  note       TEXT,
  changed_by TEXT NOT NULL,               -- 'claude' | 'user'
  changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE runs (
  id           INTEGER PRIMARY KEY,
  started_at   TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at  TEXT,
  trigger      TEXT NOT NULL,              -- scheduled | manual
  found        INTEGER DEFAULT 0,
  new_jobs     INTEGER DEFAULT 0,
  tailored     INTEGER DEFAULT 0,
  needs_you    INTEGER DEFAULT 0,
  errors       TEXT DEFAULT '[]',          -- JSON array of {source, message}
  status       TEXT NOT NULL DEFAULT 'running'  -- running | ok | partial | failed
);

CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- seeded keys: max_tailored_per_run=5, min_hours_between_runs=4,
--              telegram_enabled=1, ui_base_url=http://localhost:5173
```

### Job statuses

| Status | Set by | Meaning |
|--------|--------|---------|
| `new` | Claude | Found, not yet evaluated |
| `skipped` | Claude/user | Below fit score, excluded keyword, freelance, duplicate, or "Not interested". The user can still pursue it: **Apply anyway** in the UI → `shortlisted` + `docs_requested` |
| `shortlisted` | Claude/user | Worth applying (fit ≥ the filter's `min_fit_score`) but no documents yet. Documents are written automatically only if `fit_score ≥ min_fit_for_documents` (60, editable), or if the user clicked **Write documents** (`docs_requested`). Otherwise the job waits for the user's decision |
| `docs_ready` | Claude | CV + letter generated, ready for the user to apply |
| `needs_attention` | Claude | Human needed: `needs_login`, `captcha`, `form_unclear`, `missing_profile_info`, `german_only_form`, `source_error`, `work_authorization`, `below_blue_card_threshold` (see §5a), `inferred_facts` (R5/R9, §7) |
| `applied` | **user only** | User submitted |
| `interview`, `offer`, `rejected`, `withdrawn` | **user only** | Pipeline tracking |

Every status change writes a row to `status_history`.

---

## 5. Job sources

All adapters implement one protocol in `core/sources/base.py`:

```python
class Source(Protocol):
    key: str                                   # "ba_jobsuche"
    def search(self, f: SearchFilter, limit: int) -> list[JobPosting]: ...
    def fetch_details(self, job: JobPosting) -> JobPosting: ...  # fill description if search lacked it
```

Adapters are registered in a dict `SOURCES = {key: instance}`. **Adding a board = one new file +
one registry line.** Each adapter maps the filter to its own parameters and returns normalised
`JobPosting` objects. Unsupported filter fields are ignored by the adapter and applied afterwards
in Python (or by Claude for `work_mode`).

| Key | Board(s) | Type | Notes |
|-----|----------|------|-------|
| `ba_jobsuche` | Bundesagentur für Arbeit | Public REST API | Base `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service`, header `X-API-Key: jobboerse-jobsuche`. Params include `was`, `wo`, `umkreis`, `angebotsart=1`, `arbeitszeit` (`vz`, `tz`, `ho` = Homeoffice, `mj` = Minijob …), `veroeffentlichtseit`, `page`, `size`. **Verify endpoints and params against the community docs (github.com/bundesAPI/jobsuche-api) before coding — they change.** Verified live 2026-10-15: search `/pc/v6/jobs` (v4 → 403), details `/pc/v4/jobdetails/{base64(referenznummer)}`. Germany-wide filters send `wo=Deutschland`, otherwise BA mixes in Austrian EURES jobs. |
| `arbeitnow` | Arbeitnow | Public JSON API | `https://www.arbeitnow.com/api/job-board-api`, paginated via `links.next`; has a `remote` flag and `tags`. Filter keywords/location client-side. |
| `jobspy` | Indeed (DE), LinkedIn, Glassdoor | **Scraping** via `python-jobspy` | `scrape_jobs(site_name=[…], search_term=…, location=…, country_indeed="germany", hours_old=…, results_wanted=…, linkedin_fetch_description=True)`. Keep `results_wanted` small (≤20/site/run). LinkedIn is the most likely to block — treat its failure as normal. Google Jobs was removed (user decision 2026-10-15): it returned nothing for every filter. |

Also built: `email_alerts` (job-alert emails, §5b, Phase 9). Planned later (same interface): RemoteOK (API),
We Work Remotely (RSS), Berlin Startup Jobs, Get in IT, and a `manual` source where the user
pastes a URL in the UI.

### Deduplication (`core/dedup.py`)
1. **Canonical URL:** lowercase host, drop `www.`, strip tracking params (`utm_*`, `ref`, `trk`,
   `refId`, `trackingId`, `gclid`, `fbclid`, …), strip fragments and trailing slashes. For known
   boards, reduce to the stable job ID form (e.g. LinkedIn `/jobs/view/<id>`).
2. **Fingerprint:** `sha1(normalise(company) | normalise(title) | normalise(city))`, where
   normalise lowercases, removes `(m/w/d)`, `(w/m/d)`, `(all genders)`, `GmbH/AG/SE/KG`,
   punctuation, and collapses whitespace.
3. A job is **seen** if either key exists. Same job from two boards → keep the first, skip the other.

### 5a. Screening checks (`core/checks.py`, built in Phase 2)
These checks are deterministic Python code, not Claude's judgement. They run on every newly
inserted job during search (after `fetch_details`, so the full ad text is available).

**Salary vs. EU Blue Card**
- Normalise `salary_text` to **gross EUR per year**: monthly × 12, hourly × 40 × 52, `k`/`Tsd.` ×
  1000, German and English number formats (`45.934,20`, `45,934.20`). Non-EUR amounts count as
  unknown.
- For a range, use the **upper value**.
- Store the result in `jobs.salary_annual_eur` and `jobs.salary_flag`:
  - `ok`: at or above the threshold;
  - `below_blue_card_threshold`: below the threshold. The job also gets status `needs_attention`
    with this reason;
  - `salary_unknown`: no salary given, or it can't be parsed. Informational only, the job
    continues normally and Claude mentions it in `fit_notes`.
- The threshold is an editable setting, never hardcoded: `blue_card_salary_min = 45934.20` and
  `blue_card_salary_year = 2026`. Update both each January (UI `/settings`).

**Work authorization**
- Scan the ad text (title + description) case-insensitively for demands the user must answer
  personally. German: `unbefristete Arbeitserlaubnis`, `uneingeschränkte Arbeitserlaubnis`,
  `EU-Staatsbürgerschaft`. English: `EU citizen only`, `EU citizens only`, `no visa sponsorship`,
  `right to work without sponsorship`, `unrestricted work authorization`.
- On a match, set status `needs_attention` with reason `work_authorization`, and put the matched
  phrase in the detail.
- `apply-assist` (Phase 8) checks the live application form again for the same phrases (§13).

Phase 2 adds migration `002_screening.sql`: the `jobs.salary_annual_eur REAL` and
`jobs.salary_flag TEXT` columns, the two settings, and unit tests for salary parsing and keyword
matching.

### 5b. Email-alert source (`core/sources/email_alerts.py`, Phase 9, built 2026-10-15)

**As built:**
- **Senders:** in the user's ALERTS inbox only LinkedIn (and, since 2026-10-16, Instaffo) sends alerts:
  `jobalerts-noreply@` (job alerts), `jobs-noreply@` (recommendations) and `messages-noreply@`
  ("… is hiring"), all `@linkedin.com`. These three are seeded in `alert_senders`.
  `security-noreply@linkedin.com` is never read.
- **Parsing:** the plain-text part, where each `linkedin.com/comm/jobs/view/<id>` link has the
  title / company / location (or "Company · Location (Mode)") above it. HTML link text is the
  fallback.
- **StepStone/XING:** no alerts from them so far. Their link parser, redirect resolver and
  `dedup.py` ID rules are written, but **unverified**: check them with the first real
  StepStone/XING alert, then add their sender addresses in `/settings`.
- **Dry runs:** `run_search(dry_run=True)` sets `adapter.dry_run`, so a dry run records no
  `alert_messages` rows and doesn't advance `email_alerts_last_success`.
- **Migration 009** adds `email_alerts` to every existing filter's `sources` (and to the
  `SearchFilter` default).
- **Live acceptance, 2026-10-15** (on a DB copy):
  - 26 mails → 120 jobs, of which 27 matched the filters' keywords: 22 new, 5 already known from
    jobspy LinkedIn;
  - flags identical before and after; 0 HTTP requests;
  - a second pass made 0 full-message fetches.
Reads the job-alert emails that LinkedIn, StepStone and XING send to the user, and turns them into
`JobPosting`s like any other adapter (key `email_alerts`, same `Source` protocol and registry).
**No LinkedIn login, no use of the user's board accounts, no cookies, and no scraping with the
user's account.** The emails are the only input.

**Mailbox access (strictly read-only)**
- Uses the **ALERTS** account (`mail_config.load_alerts_config()`), falling back to the SEND
  credentials if ALERTS is empty. Not necessarily Yahoo: host and port come from `.env`.
- Opens the folder with `EXAMINE` (read-only), never `SELECT`. Fetches with `BODY.PEEK[...]` only,
  so no flags change, and messages are **not** marked as seen. Never `STORE`, `COPY`, `MOVE`,
  `EXPUNGE` or `APPEND`. The ALERTS config can't create drafts (`mail_drafts` checks the role).
- Selects alerts **by sender, not by unread status**:
  `UID SEARCH SINCE <date> (OR FROM a FROM b …)`. `<date>` is the date of the last successful
  `email_alerts` read (setting `email_alerts_last_success`), or 14 days ago on the first run.
  IMAP `SINCE` only has day granularity, so the overlap is handled by the Message-ID table below.
- Fetches `BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM DATE)]` first and skips Message-IDs already in
  `alert_messages`. Only new messages get a full `BODY.PEEK[]`.

**Settings (editable, UI `/settings`, never hardcoded)**
- `alert_senders`: a JSON list of `{"board": "linkedin" | "stepstone" | "xing", "from": "<address>"}`.
  Seed it from the senders actually found in the user's ALERTS inbox when building, e.g.
  LinkedIn's `jobalerts-noreply@linkedin.com`. Don't guess the StepStone and XING addresses;
  confirm them with the user.
- `alert_folder`: default `INBOX`, for users who sort alerts into a folder.
- `email_alerts_last_success`: ISO date, written by the adapter.

**Extraction and URLs**
- For each alert email, a parser per board extracts title, company, location and job URL from the
  HTML part (text part as fallback).
- **LinkedIn:** reduce every job link (`/jobs/view/<id>`, `/comm/jobs/view/<id>`, tracking
  parameters) to `https://linkedin.com/jobs/view/<id>` from the URL alone. No request is made to
  linkedin.com.
- **StepStone / XING:** alert links are tracking redirects. Resolve each one to the final job URL
  with an anonymous GET (follow redirects, no cookies, no credentials) under R6:
  - at least 3 s between requests per host;
  - at most 40 resolutions per run;
  - stop resolving for the run on a 429/403 and record the error.

  Then apply `canonical_url` (add StepStone/XING stable-ID rules to `dedup.py`).
- Dedup is the same as for the other sources: `canonical_url` and `fingerprint`, and `is_seen`
  before any work (R8).
- `fetch_details` makes no extra request:
  - StepStone/XING: the description may come from the public page already fetched while
    resolving the redirect.
  - LinkedIn: no description, so the §5a checks and Claude's evaluation use title/company only,
    and `fit_notes` says the description was not available.

**Processed messages** (migration `00x_email_alerts.sql`)
```sql
CREATE TABLE alert_messages (
  message_id   TEXT PRIMARY KEY,
  board        TEXT NOT NULL,              -- linkedin | stepstone | xing
  received_at  TEXT,
  jobs_found   INTEGER NOT NULL DEFAULT 0,
  status       TEXT NOT NULL,              -- processed | failed
  attempts     INTEGER NOT NULL DEFAULT 1,
  processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```
- A message is recorded as `processed` once all its links are extracted and resolved.
- If a redirect can't be resolved, the message is not recorded, so it is retried on the next run.
  After 3 failed attempts it is recorded as `failed`.
- `email_alerts_last_success` only advances when a read finished without errors.
- The alert emails are parsed once per run (cached in the process). Each filter keeps the postings
  whose title matches its keywords, as with Arbeitnow.
- Alert jobs that match **no** active filter's keywords are **not stored** (user decision). Their
  message still counts as `processed`.

---

## 6. MCP server tools (`mcp_server/server.py`)

Server name: `jobhunter`. Registered in `.mcp.json`:

```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server.server"]
    }
  }
}
```

| Tool | Input | Output / effect |
|------|-------|-----------------|
| `start_run` | `trigger` | Returns `run_id`, or refuses if a run finished < `min_hours_between_runs` ago or one is still `running` |
| `get_active_filters` | — | List of active `search_filters` |
| `get_settings` | — | Settings dict |
| `search_jobs` | `filter_id`, `sources?`, `limit?` | Runs adapters, dedups, **inserts only unseen jobs** as `new` (or `needs_attention` if a §5a check hits), returns the new jobs (id, title, company, location, short description). Records per-source errors on the run. |
| `is_seen` | `url` | `{seen: bool, job_id?, status?}` |
| `get_job` | `job_id` | Full job incl. description |
| `get_profile` | — | Parsed `profile.yaml` |
| `evaluate_job` | `job_id`, `fit_score`, `fit_notes`, `work_mode`, `employment_type`, `language`, `apply_method`, `apply_email?`, `decision` (`skip`/`shortlist`), `project_suggestions?` | Stores Claude's evaluation and sets status. `project_suggestions` (R11) = list of `{title, scope, days, covers}`, stored in `jobs.project_suggestions` (JSON) |
| `render_documents` | `job_id`, `doc_language`, `cv_content` (JSON per template schema), `letter_content` (JSON) | Renders Typst → `output/<job_id>/cv.pdf`, `anschreiben.pdf` (or `cover_letter.pdf`), returns paths |
| `save_application` | `job_id`, `summary`, `interview_prep`, `method` | Creates `applications` row, sets status `docs_ready` |
| `flag_attention` | `job_id`, `reason`, `detail` | Status `needs_attention` |
| `save_email_draft` | `job_id`, `subject`, `body` | Creates an IMAP draft in the **SEND** account with the PDFs attached; sets `email_draft_saved=1`. Never sends, never uses the ALERTS account. |
| `list_jobs` | `status`, `limit?`, `for_documents?` | Brief rows (no description): `new` newest posting first, `shortlisted` highest fit score first. With `for_documents=true`: only shortlisted jobs with `fit_score ≥ min_fit_for_documents` or `docs_requested`, requested ones first. Needed for the carry-over in §10 |
| `get_apply_kit` | `job_id` | §13 kit: URL, PDF paths, field values (name, first/last, contact, address parts, earliest start, hours, salary text, links, short motivation = opening of the job's letter, else `motivation[filter]`, else summary), and the browser-extension prompt. `core/apply_kit.py`, mirrored in `ui/src/lib/server/kit.ts` |
| `check_work_authorization` | `text` | §5a phrase check on live form/page text → `{match}`. On a match, apply-assist leaves those questions empty and calls `flag_attention(work_authorization)` |
| `current_run` | — | The id of the run that is still `running` (or null). Used by the writer stage of `run.ps1` (§10) |
| `finish_run` | `run_id`, `failed_reason?` | Closes the run and sends the Telegram message (§8). Counts come from the DB: found/new from `search_jobs`; tailored and needs_you from `status_history` since the run started |

Tools validate input and return clear error messages. All DB writes go through `core/`, never raw
SQL in the server file.

Implementation notes (Phase 3):
- `start_run` returns `{started: false, reason}` instead of an error when refused. A run still
  `running` after 3 h is treated as dead, closed as `failed`, and does not block. Failed runs don't
  count for the time guard.
- `search_jobs` takes an optional `run_id` (default: the currently running run) and adds its
  errors and `found`/`new_jobs` counts to it; each new job in the result includes its `url`.
- `evaluate_job` only accepts jobs with status `new`, and refuses `shortlist` below the filter's
  `min_fit_score`.
- `save_application` picks up the PDFs `render_documents` wrote to `output/<job_id>/` and also
  writes `notes.md` (§7), because headless runs can't write files themselves. If the documents
  contain inferred facts, it sets `needs_attention` (`inferred_facts`) instead of `docs_ready`,
  and `save_email_draft` refuses until the user has approved them.
- `render_documents` (Phase 4) gets the photo from `profile.yaml` (German CVs only) and the posting
  text from the job, for the visa check.
- Telegram (Phase 5): `finish_run` sends one message: the summary line, one `❌ <source> failed`
  line per failed source, and one `⚠️` line (with a UI link) per job that went to needs_attention
  during the run, capped at 10.

---

## 7. Documents

### `profile/profile.yaml` (user-maintained; ship `profile.example.yaml`)
Sections: `personal` (name, address, email, phone, nationality optional, birthdate optional,
photo path optional), `summary_de` / `summary_en`, `experience[]` (company, role, city, from, to,
bullets_de[], bullets_en[], tech[]), `education[]`, `skills` (grouped), `languages[]` with CEFR
levels, `projects[]`, `certificates[]`, `availability` (hours per week, start date),
`work_authorization` (free text the user writes themselves), `preferences` (salary text, notes).
New fields (2026-10-15):
- `motivation`: a map keyed by **search-filter name**, e.g. `"AI / LLM / Data": "…"`. The user's
  own reasons for that category, which they update from time to time; they may be empty.
- `education[].grade_de`: the German-scale equivalent of the CGPA, computed with the modified
  Bavarian formula `1 + 3·(Nmax − Nd)/(Nmax − Nmin)` and confirmed by the user. It is replaced by
  the ZAB/uni-assist value once that exists.
- `education[].focus_de` / `electives_de`: German course names for German letters. These are
  translated once and checked by the user, not translated freshly in every run.

### Building `profile.yaml` (Phase 1)
Fill it from: the user's CV (they will provide it), their website and LinkedIn, their GitHub
(pick the strongest public projects), and their degree transcript/curriculum. Show the draft to the user and ask about every gap — dates, employers,
grades, certificates — instead of guessing (R5). Language certificates belong in `languages[]`.

### Rules for tailoring
- **Language:** documents match the posting language (`de` → German, `en` → English).
- **German CV (Lebenslauf):** tabular, reverse-chronological, max 2 pages, photo only if
  `photo` is set, dates as `MM/YYYY`, no invented signature.
- **German Anschreiben:** DIN 5008 layout, formal *Sie*, Betreffzeile instead of "Betreff:",
  date top right, max 1 page, closing "Mit freundlichen Grüßen", correct umlauts (ä ö ü ß).
- **English:** one-page cover letter, CV max 2 pages.
- Reorder and select existing bullets and skills to match the posting; mirror the posting's key
  terms **only where truthful** (R5).
- **Location/language fit note (cover letter):** only when relevant to the posting, add one short
  sentence that the user already lives in Germany (from `personal.address`) and/or speaks German
  at their level (from `languages[]`) — e.g. when the role is on-site/hybrid, German-speaking, or asks for
  an early start. Skip it when it adds nothing.
- **No visa talk in the first application:** never mention visa, residence permit, Blue Card or
  work authorization in the CV or cover letter unless the posting explicitly asks for it. Forms
  that ask are handled by the user (§5a, §13).

**Cover-letter style rules** (user, 2026-10-15). Written by the writer stage (Sonnet).
1. **No clichéd openers** such as "mit großem Interesse habe ich Ihre Anzeige gelesen",
   "hiermit bewerbe ich mich", "I am writing to apply" or "I am applying for". Open with a
   motivation tied to *this* role and company.
2. **Motivation** comes from `profile.motivation[<filter name of the job>]`. If that entry is
   missing or too thin for a convincing opening, write the best truthful opening from profile
   facts. Also add `⚠️ Motivation for "<filter name>" missing/thin in profile.yaml` to the summary
   (and so to `notes.md`), and `finish_run` lists those categories in the Telegram message.
   Motivation is never invented.
3. **German letters use German course names** (`focus_de` / `electives_de`), never the English
   originals.
4. **Grades:** next to the CGPA, give the German equivalent from `grade_de`, e.g.
   "CGPA 3,45/4,00 (entspricht ca. 1,8 nach der modifizierten bayerischen Formel)". If `grade_de`
   is missing, give the CGPA only. The conversion is never computed ad hoc.
5. **Strong verbs:** concrete actions (entwickelt, aufgebaut, eingeführt, automatisiert,
   betreut) instead of weak ones such as "unterstützt" or "mitgewirkt", but only where the
   profile backs the stronger claim (R5).
6. **Correct German compounds** with a hyphen: IT-Leiter, Full-Stack-Entwickler,
   Backend-Entwicklung, CI/CD-Pipeline.
7. **4–5 short paragraphs** in the body.
8. **Ending:** the last paragraph states availability / start date (`availability.start_date`,
   `hours_per_week`). The letter ends with the user's **full name** (`personal.name`, from the
   template).
9. **Project links:** every project mentioned in the letter carries its GitHub/URL from
   `projects[].url`.

`core/docs.py` enforces 1, 7, 8 and 9 deterministically:
- a cliché-opener regex;
- 4–5 body paragraphs;
- the last paragraph contains the start date, "ab sofort" or "immediately";
- each profile project named in the letter has its URL in the letter.

`render_documents` refuses violations with a message that says what to fix. Rules 2–6 are in the
skill.
- `notes.md` per job: posting snapshot, fit score + reasons, what was emphasised, gaps, and
  interview prep (likely questions, technical topics to revise, questions to ask them).

- **Inferred facts (R5/R9):** a skill or statement that the profile implies but doesn't state
  (e.g. a related tool where the profile shows the neighbouring skill at a solid level) may go into
  the documents only if it is listed in that document's `inferred` array as
  `{text, where, basis}`, with `basis` naming what in the profile implies it. `render_documents`
  records the list in `output/<job_id>/content.json`. `save_application` then sets
  `needs_attention` (`inferred_facts`) and lists them at the top of `notes.md`. The user approves
  them in the UI (→ `docs_ready`) or has the documents re-rendered without them. Facts that aren't
  implied are never added.
- **R9 enforcement (code):** `render_documents` refuses an inferred entry that claims years,
  employers, grades or certificates, and any document that contains a statement from
  `rejected_inferences` (migration 006, a table). **Reject** in the UI records the job's inferred
  facts there and sets the job back to `shortlisted`. `get_profile` returns the list, so Claude
  sees what not to reuse.
- **R10/R11** are part of the `job-hunt` skill: at most 2–3 relevant items per letter, each tied
  to a requirement, and project ideas for gaps only in `fit_notes`. In the CV, experience and
  education stay chronological (sorted by `docs.py`); projects and skills are ordered by relevance.

Templates take a JSON data file (`sys.inputs` / `json()` in Typst). Keep layout in Typst, content
in JSON — Claude only produces content.

**Phase 4 implementation:**
- `templates/{cv,letter}_{de,en}.typ` are thin entry files over `templates/lib/{cv,letter}.typ`.
- The content schema, with full examples, is in `templates/examples/*.json`.
- `core/docs.py` checks before writing any file:
  - unknown or missing keys;
  - the subject starts with "Betreff:";
  - visa or work-authorization wording that the posting itself doesn't contain;
  - inferred entries without a basis;
  - page limits: CV ≤ 2, letter exactly 1.
- Output: `cv.pdf`, plus `anschreiben.pdf` (de) or `cover_letter.pdf` (en; a language switch deletes
  the other letter), plus `content.json`.
- The font is Calibri, falling back to Carlito/Arial. The letter date defaults to today, formatted
  as `15.10.2026` or `15 October 2026`.

---

## 8. Notifications (`core/notify.py`)

`POST https://api.telegram.org/bot<TOKEN>/sendMessage` with `chat_id`, `parse_mode=HTML`,
`disable_web_page_preview=true`. `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
`cli.py telegram-setup` reads `getUpdates` and prints the chat ID after the user messages the bot.

| Event | Message |
|-------|---------|
| Run finished | `🔎 Run 08:02 — 23 found · 6 new · 4 docs ready · 2 need you` |
| Needs attention | `⚠️ <b>Backend Developer (m/w/d)</b> – Company, City: needs_login` + UI link |
| Source error | `❌ linkedin failed this run (others OK)`, only when the source gave nothing in **all** its searches. Otherwise `⚠️ linkedin: no results for 2 of 6 filters` (soft) or `⚠️ ba_jobsuche: errors in 1 of 6 filters`. Migration 008 `runs.source_searches` counts searches per source; errors carry their `filter_id`. Run status: `partial` only for a real error or a source that failed completely; a few "no results" keep it `ok` |
| Run failed | `🛑 Run failed: <short reason> — see logs/<file>` |

Telegram failures must never fail a run; log and continue.

---

## 9. Scheduled runs

### `run.ps1`
1. `Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue` (R7).
2. `cd` to the project folder; write a timestamped log to `logs/`.
3. Run: `claude -p "Run the job-hunt workflow defined in .claude/skills/job-hunt/SKILL.md. Trigger: scheduled."`
4. On non-zero exit, send a Telegram "Run failed" message via `uv run python cli.py notify-failure`.

### `.claude/settings.json`
Headless runs cannot answer permission prompts, so pre-approve only what the workflow needs:
the `jobhunter` MCP tools (`mcp__jobhunter__*` / `mcp__jobhunter`), `Read` inside the project,
and nothing that sends data elsewhere. Do **not** allow arbitrary Bash or web access in headless
mode. Verify the exact permission-rule syntax against current Claude Code docs.

### `setup-task.ps1`
Registers task `JobHunter`: daily triggers 08:00 and 18:00, `-StartWhenAvailable` (catch up after
the PC was off), `-WakeToRun`, `-RunOnlyIfNetworkAvailable`, `-ExecutionTimeLimit 2h`, runs as
the current user only when logged on. Idempotent (re-running updates the task).
`min_hours_between_runs` in the DB is the second guard against double runs.

---

## 10. The `job-hunt` skill (`.claude/skills/job-hunt/SKILL.md`)

Workflow Claude follows on every scheduled run:

1. `start_run`. If refused, stop quietly.
2. `get_settings`, `get_profile`, `get_active_filters`.
3. For each filter: `search_jobs`.
4. For each new job: read it (`get_job`), then `evaluate_job`:
   - classify `work_mode`, `employment_type`, `language`, `apply_method`;
   - skip if freelance/self-employed and `exclude_freelance`, if it matches `exclude_keywords`,
     if the employment type isn't wanted, or if `fit_score < min_fit_score`;
   - if `salary_flag = salary_unknown`, mention it in `fit_notes`;
   - otherwise `shortlist`.
   (Jobs already flagged `needs_attention` by the §5a checks in `search_jobs` are not evaluated.)
5. Take `list_jobs("shortlisted", for_documents=true)` up to `max_tailored_per_run`: jobs with
   `fit_score ≥ min_fit_for_documents` (setting, default **60**) or `docs_requested` by the user.
   Write CV + letter content → `render_documents` → `save_application`.
   If `apply_method = email` and `apply_email` exists → `save_email_draft`.
   If something blocks (e.g. profile lacks a required item) → `flag_attention`.
6. `finish_run` with counts.

**Two stages, two models** (user decision 2026-10-15). `run.ps1` runs `claude -p` twice:

| Stage | Steps | Model (setting) | Prompt |
|---|---|---|---|
| 1 Filter | 1–4: start_run, search, evaluate/score, extract fields, R11 project suggestions | `model_filter` = **haiku** | "…Stage: filter." |
| 2 Writer | 5–6: CV + letter, save_application, email draft, finish_run | `model_writer` = **sonnet** | "…Stage: write." |

- Stage 2 runs only if stage 1 left a run open (`cli.py check-run`). It picks the run up with
  `current_run`.
- If stage 1 fails, `notify-failure` closes the run as before. If stage 2 fails, the run is
  closed as failed too, but the evaluations from stage 1 are kept.
- Migration 007 replaces the setting `run_model` with `model_filter` and `model_writer`. Both are
  editable in `/settings`.
- The threshold `min_fit_for_documents` defaults to **60** (user, 2026-10-15) and is editable in
  `/settings`. It equals the default filter `min_fit_score`, so every shortlisted job currently
  gets documents; raise it to be pickier.
- **"Generate now"** (UI): `run.ps1 -Trigger docs` runs only the writer stage as a separate run
  with trigger `docs`. It does `start_run("docs")`, writes documents for the jobs with
  `docs_requested` (`list_jobs(..., requested_only=true)`), then `finish_run`. Docs runs skip
  `min_hours_between_runs` and don't count for it, but never start while another run is running.

Remaining shortlisted jobs carry over to the next run. Keep the run within Pro usage limits:
short evaluations, full tailoring only for the capped top jobs.

Usage caps (settings, migration 004):
- `search_limit_per_source = 10` is the default `limit` for `search_jobs`.
- `max_evaluated_per_run = 30`: step 4 evaluates `list_jobs("new", limit=30)`, newest first.
  Older `new` jobs carry over to the next run.

**Model history:**
- `run_model` (migration 005) used one model for the whole run. In a test on 2026-10-15, Haiku
  evaluated and tailored correctly (no invented facts, valid documents, 2 minutes / 30 turns
  against about 12 minutes / 89 turns on Opus), but its letters were less specific.
- It is superseded by the two-stage split above: Haiku filters and scores, Sonnet writes.

`run.ps1` details:
- It runs `claude -p` with `--mcp-config .mcp.json --strict-mcp-config` (only the jobhunter
  server, none of the user's other connectors) and `--permission-mode dontAsk` (anything not
  allowed is denied, never prompted).
- It also passes `--disallowedTools` for Bash, PowerShell, Write, Edit, NotebookEdit, WebFetch and
  WebSearch, and `--output-format json`, so the log ends with the result and any permission
  denials.
- `.claude/settings.json` allows `mcp__jobhunter` and `Read(/**)`, denies `Read(/.env)` (R3), and
  sets `enabledMcpjsonServers: ["jobhunter"]`.
- After claude exits, `cli.py check-run --since <start>` makes sure the run was closed. If claude
  exited non-zero or the run is still open, `cli.py notify-failure` marks open runs as failed and
  sends `🛑 Run failed`.

---

## 11. CLI (`cli.py`, for development and manual use)

`init-db` · `seed-filters` · `search --filter 1 --source arbeitnow --dry-run` ·
`render-test` (renders templates with example data) · `telegram-setup` · `telegram-test` ·
`mail-test [--account send|alerts]` (default `send`: logs in to `SEND_IMAP_HOST`, lists folders,
finds the Drafts folder via the `\Drafts` special-use flag with `Draft`/`Drafts` name fallback,
does **not** create a draft unless `--create`; the test draft goes to your own address with
subject `JobHunter test`. `alerts`: login and folder list only; `--create` is refused) ·
`notify-failure`.

---

## 12. Web UI (`ui/`, SvelteKit at http://localhost:5173)

| Page | Content |
|------|---------|
| `/` Jobs | Table: title, company, location, work mode, fit score, status, first seen. Filter by status/source/work mode, search box. "Needs you" count badge in the header. **Pagination**: 50 per page (`?page=N`, page size selectable 25/50/100), with prev/next and "x–y of z". **Sorting**: click a column header (title, company, location, mode, fit, status, first seen) to sort; click again to reverse (`?sort=fit&dir=desc`; a fit score of "none" sorts last). Filters, sort and page stay in the URL. Row buttons: **Apply anyway** (skipped) / **Write docs** (no documents yet) and ✕ Not interested. A banner with **Generate now** appears while requested documents are waiting. |
| `/jobs/[id]` | Full posting, fit notes, **Project suggestions** (R11: own section from `jobs.project_suggestions`: title, scope, days, requirement covered), status dropdown + note (writes `status_history` with `changed_by='user'`), "Mark as applied" (sets `applied_at`), links to PDFs, `notes.md` rendered, interview prep, history timeline, **Apply kit** panel (§13). Buttons: **Apply anyway** on skipped jobs (→ `shortlisted` + `docs_requested`) and **Write documents** on shortlisted jobs below the threshold (→ `docs_requested`). The next run's writer stage then tailors them even if the fit is below the threshold. Also available as a row button in the Jobs list. |
| `/attention` | Only `needs_attention` jobs with reasons and what to do. For `inferred_facts`: the list (statement, where, basis) with **Approve** (→ `docs_ready`, sets `applications.inferred_approved_at`, `changed_by='user'`) and **Reject** (back to `shortlisted` for a re-render without them). |
| `/filters` | List, create, edit, toggle active, delete search filters (all fields in §4). |
| `/runs` | Run history with counts and per-source errors. |
| `/settings` | `max_tailored_per_run`, `min_hours_between_runs`, Telegram on/off, "Run now" button (spawns `run.ps1` with trigger `manual`). |

Server-side only DB access (`+page.server.ts`, form actions). Serve PDFs through a route that
only reads from `output/`. Bind to `127.0.0.1` only. Simple, clean design; light/dark mode.

**Not interested** (user request): a button on `/`, `/jobs/[id]` and `/attention` moves a job to
`skipped`, with `changed_by='user'` and the note "not interested". This is different from
`rejected`, which means the employer rejected the user.

**Phase 6 implementation:**
- SvelteKit 2 + Svelte 5 + better-sqlite3. All SQL is in `ui/src/lib/server/db.ts`; the schema
  stays owned by `core/migrations`.
- `ui/src/hooks.server.ts` only serves Host `localhost`/`127.0.0.1` and rejects non-GET requests
  without a same-origin `Origin`. SvelteKit skips its own CSRF check in dev mode.
- The user can set any status except `needs_attention` (that one needs a reason).
- On `/attention`, "Resolved" sets a job that was never evaluated back to `new` (the next run
  evaluates it), and an evaluated one to `shortlisted`.
- `/files/<id>/<name>` serves only `cv.pdf`, `anschreiben.pdf` and `cover_letter.pdf` from
  `output/<id>/`.
- Markdown (`notes.md`, fit notes) is rendered with raw HTML escaped.
- Run it with `cd ui; npm run dev`, or `npm run build` + `npm start` (`serve.js`). Both bind to
  `127.0.0.1:5173` unless `UI_LAN=1`.

**Hotspot access** (user request 2026-10-15: devices on the PC's Mobile Hotspot). This deliberately
relaxes "bind to 127.0.0.1 only":
- `.env`: `UI_LAN=1`, `UI_LAN_SUBNETS=192.168.137.0/24` (the Windows hotspot), and
  `UI_SESSION_SECRET` (R3: in .env only, never shown in the UI).
- With `UI_LAN=1`, the server binds to `0.0.0.0`. `hooks.server.ts` (`lib/server/access.ts`) then
  decides by client IP:
  - loopback is let in as before;
  - clients in the subnets need a signed `jh_device` cookie (HttpOnly, SameSite=Strict, 1 year);
  - every other client gets 403.
  - On 2026-10-15 the user also enabled the home Wi-Fi (`192.168.0.0/24`, PC address
    `192.168.0.157`): `UI_LAN_SUBNETS=192.168.137.0/24,192.168.0.0/24`. Traffic there is plain HTTP,
    so the network must be trusted.
- A device pairs on `/login` with a 6-digit code that only the PC can create (Settings → Pair a
  device). The code is valid for 10 minutes, works once, and is burned after 5 wrong tries.
- Changing `UI_SESSION_SECRET` signs out every device. The same-origin check applies to all
  write requests.
- `serve.js` runs its own HTTP server that sets the protocol header, because adapter-node otherwise
  assumes https and the same-origin check rejects every form.

---

## 12b. Additions 2026-10-16 (user requests)

**Document file names.** PDFs are named `<Name>_<Job_title>_<Document>.pdf`:
- the name comes from `personal.name` and the title from the job; gender tags are dropped,
  umlauts transliterated, and the result is ASCII-safe for upload forms;
- `<Document>` is `Lebenslauf` / `Anschreiben` (de) or `CV` / `Cover_Letter` (en).

`core/applications.py` (`document_filename`, `classify_document`, `list_documents`) is the single
source; `ui/src/lib/server/files.ts` mirrors `classify_document`. The UI serves only names that
classify as a document. The legacy names `cv.pdf` / `anschreiben.pdf` / `cover_letter.pdf` are
still recognised; `cli.py rename-documents` renamed the existing ones.

**Jobs added by hand, and full postings** (`core/manual.py`):
- **Adding a job:** `add-job` (CLI) or **+ Add a job** (UI) takes a link and/or pasted text.
  - `is_seen` comes first (R8): a known job gets the pasted text instead.
  - Public pages are fetched with **one** anonymous GET (no cookies). The fetch reads
    schema.org JSON-LD, then schema.org microdata (SAP SuccessFactors sites such as adesso), then
    the page title + text. SmartRecruiters links use its public Posting API.
  - linkedin.com, instaffo.com and xing.com are **never** fetched (login / SSO); the user pastes
    the text.
  - The job is filed under the first active filter whose keywords match its title, gets a salary
    line from the text if there is one, and is screened (§5a).
- **Full postings:** `update-posting` (CLI) or **Full posting → Save** (UI) replaces a job's
  description, e.g. for email-alert jobs that only have a title. It screens the job again,
  clears its evaluation and sets it back to `new`.
- **Evaluate now:** `run.ps1 -Trigger single -JobId N` runs stage `single` (Haiku evaluates job
  N), then stage `single-write` (Sonnet writes its documents if it is shortlisted with
  `fit_score ≥ min_fit_for_documents`, or if the user requested them), then `finish_run`.
  Trigger `single`, like `docs`, skips the time guard and doesn't count for it.

**Instaffo alerts** (`notifications@app.instaffo.com`, migration 010):
- `parse_instaffo` reads the job-suggestion cards from the mail text: title, company, city,
  skills, salary and work mode, in both the current German and the older English labels.
- Instaffo links carry an SSO login token, so they are **never opened** (R2). The token never
  reaches the DB: the job URL is rebuilt from the job's UUID, and `sso` / `token` / `auth` /
  `session` / `sid` are stripped by `canonical_url`.
- Most Instaffo mails are reminders or application updates; they yield 0 jobs and are recorded
  as processed.

## 13. Apply assist (interactive, user present)

The UI's **Apply kit** shows: the application URL, the PDF file paths, and copy buttons for
common fields (name, email, phone, address, earliest start, hours per week, salary text,
short motivation paragraph). It also shows a ready-made prompt for the Claude browser extension:

> "Fill in this application form using the data below. Upload the CV and cover letter if the
> form allows it. Do not click the final submit button — stop and tell me when it is ready."

`.claude/skills/apply-assist/SKILL.md` describes the same behaviour for Claude Code sessions.
R1 and R2 apply in full: the user logs in, solves CAPTCHAs and submits. Questions about work
authorization, visa or sponsorship are left blank for the user to answer; if the form demands
unrestricted work authorization (§5a phrases), flag `work_authorization`. The prompt above includes:
"Leave any work-authorization, visa or sponsorship questions empty and point them out to me."

---

## 14. Build phases

Stop after each phase, report what was built, and run the acceptance checks.

| Phase | Build | Acceptance checks |
|-------|-------|-------------------|
| **1 Foundation** | Repo layout, `pyproject.toml`, `.gitignore`, `.env.example` (generic IMAP mail settings, Yahoo defaults), `core/db.py`, migration 001, models, `profile.example.yaml`, README, `init-db`, `seed-filters` | `uv run python cli.py init-db` creates the DB; seeded filters visible; `.env` and `data/` are ignored by git |
| **2 Sources + dedup + screening** | `base.py`, `ba_jobsuche`, `arbeitnow`, `jobspy_source`, `dedup.py`, `checks.py` + migration 002 (§5a), `search` CLI | Each source returns real jobs with `--dry-run`; a second identical search inserts 0 new jobs; unit tests for URL canonicalisation, fingerprints, salary normalisation (range → upper value, monthly/hourly → yearly, missing → `salary_unknown`) and work-authorization keywords; threshold read from `settings` |
| **3 MCP server** | All tools in §6, `.mcp.json` | `claude mcp list` shows `jobhunter`; in an interactive session Claude can call `get_active_filters`, `search_jobs`, `is_seen` |
| **4 Documents** | Typst templates (DE/EN CV, DE DIN 5008 letter, EN letter), `core/docs.py`, `render-test` | PDFs render with example data; umlauts correct; CV ≤ 2 pages, letter 1 page |
| **5 Workflow + scheduling + Telegram** | `job-hunt` skill (incl. the §7 cover-letter fit-note and no-visa rules), `notify.py`, `run.ps1`, `.claude/settings.json`, `setup-task.ps1`, Telegram CLI commands | A manual `run.ps1` completes headless without permission prompts; Telegram summary arrives; an immediate second run is refused by the time guard; task appears in Task Scheduler with catch-up enabled |
| **6 Web UI** | All pages in §12 | Status change in UI appears in `status_history`; filter edits are used by the next run; PDFs open from the job page; approving inferred facts moves the job to `docs_ready` |
| **7 Mail drafts** | `mail_drafts.py`, `save_email_draft`, `mail-test` (`mail_drafts.py`, `mail_config.py` (SEND/ALERTS accounts) and `mail-test` were built early, on request) | A test draft with both PDFs appears in the SEND account's Drafts; nothing is sent. ✅ 2026-10-15: `mail-test --create --job 150` put the draft in Yahoo `Draft` with `cv.pdf` and `cover_letter.pdf`, not in Sent. Yahoo discards IMAP flags on APPEND (`\Draft` included), so the folder is what makes it a draft |
| **7a Two-model runs + letter rules** (2026-10-15) | Migration 007 (`jobs.project_suggestions`, `jobs.docs_requested`; settings `model_filter`, `model_writer`, `min_fit_for_documents=60`; drops `run_model`), two-stage `run.ps1`, `current_run`, `list_jobs(for_documents)`, `evaluate_job(project_suggestions)`, letter checks in `docs.py`, skill update (§7 style rules, R10, R11), profile `motivation` / `grade_de` / `*_de` course names, UI: pagination, project suggestions, Apply anyway / Write documents, model settings | A manual run uses Haiku for stage 1 and Sonnet for stage 2 (visible in the log JSON `modelUsage`); only jobs with fit ≥ min_fit_for_documents (60) or `docs_requested` get documents; a cliché opener, 3 or 6 paragraphs, no start date in the closing paragraph, or a mentioned project without its link are each refused by `render_documents`; project suggestions show on the job page; "Apply anyway" on a skipped job leads to documents in the next run; the Jobs list pages through 50 at a time |
| **8 Apply assist** | Apply kit panel, `apply-assist` skill (re-checks the live form for §5a work-authorization phrases) | Kit shows correct data and paths for a `docs_ready` job; a form demanding unrestricted work authorization gets flagged `work_authorization` and those fields stay empty. ✅ 2026-10-15: the UI kit for #150 is identical to `cli.py apply-kit 150`. On a local test form (placeholder data, DB copy), the page text matched "uneingeschränkte Arbeitserlaubnis", the job was flagged, 9 fields were filled, both work-authorization/visa questions stayed empty, and the form was not submitted. The UI also has a **Flag: work authorization** button for forms filled with the browser extension |
| **9 Email alerts** ✅ | `core/sources/email_alerts.py` + migration (`alert_messages`, `alert_senders`, `alert_folder`, `email_alerts_last_success`), StepStone/XING rules in `dedup.py`, `/settings` fields (§5b) | Flags of every fetched message are identical before and after a run (nothing marked seen); a second run fetches no full bodies (Message-IDs skipped); LinkedIn links come out as `linkedin.com/jobs/view/<id>` with no request to linkedin.com; StepStone/XING links resolve to final job URLs with ≥ 3 s per host; with ALERTS empty, the SEND credentials are used read-only |

---

## 15. Defaults to seed (`seed-filters`)

| Filter | Keywords | Location | Work modes | Employment | Notes |
|--------|----------|----------|------------|------------|-------|
| Software / Backend | Softwareentwickler, Software Engineer, Backend Developer, Full Stack Developer, Python Developer, Go Developer | Germany-wide | remote, hybrid, onsite | full_time | `exclude_freelance=1` |
| AI / LLM / Data | Machine Learning Engineer, AI Engineer, LLM Engineer, Data Scientist, Data Engineer, NLP | Germany-wide | remote, hybrid, onsite | full_time | `exclude_freelance=1` |
| Web / App | Web Developer, Frontend Developer, Mobile Developer, Flutter Developer, App-Entwickler | Germany-wide | remote, hybrid, onsite | full_time | `exclude_freelance=1` |
| DevOps / Cloud | DevOps Engineer, Cloud Engineer, Platform Engineer, Site Reliability Engineer | Germany-wide | remote, hybrid, onsite | full_time | `exclude_freelance=1` |
| Computer Engineering | Embedded Software Engineer, Firmware Entwickler, Computer Engineer | Germany-wide | remote, hybrid, onsite | full_time | `exclude_freelance=1` |
| Fintech / Health-tech | Fintech, Bankensoftware, Medizininformatik, Health IT, Medizintechnik Software | Germany-wide | remote, hybrid, onsite | full_time | `exclude_freelance=1` |

The defaults assume a user who is open to relocating anywhere in Germany (so on-site and hybrid
roles are wanted too) and speaks German well enough for German-language postings and documents.
The user's actual situation lives in `profile.yaml` (`personal.address`, `languages[]`,
`preferences.notes`); adjust the filters in the UI to match.

Exclude keywords for all: `Freelance`, `Freiberuflich`, `Selbstständig`, `Senior Principal`.
For the BA source, map `full_time` to `arbeitszeit=vz` (plus `ho` when remote is wanted). BA
treats the `arbeitszeit` list as OR, so `ho` is only added when remote is wanted and on-site is
not; otherwise it would only widen the results.
All filters stay editable in the UI (`/filters`).
