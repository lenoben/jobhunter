# JobHunter core: sources, MCP server, documents, notifications

Part of the JobHunter blueprint (root `CLAUDE.md`, whose hard rules R1–R11 apply here too).

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
| `jobspy` | Indeed, LinkedIn, Glassdoor | **Scraping** via `python-jobspy` | Per target country (§16a): `scrape_jobs(site_name=[…], search_term=…, location=…, country_indeed=<country>, hours_old=…, results_wanted=…, linkedin_fetch_description=True)`. Keep `results_wanted` small (≤20/site/run). LinkedIn is the most likely to block — treat its failure as normal. Google Jobs was removed (user decision 2026-10-15): it returned nothing for every filter. |

Also built: `email_alerts` (job-alert emails, §5b, Phase 9), `himalayas` and `jobicy` (remote jobs, §16a).
Remotive and Remote OK were tested on 2026-10-25 and left out: Remotive's free API had 10 jobs in
total, Remote OK 99 mostly old ones. Planned later (same interface): We Work Remotely (RSS), Berlin Startup Jobs, Get in IT, and a `manual` source where the user
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
- Both checks only run with `work_permit_checks = 1` (default; core §16). With `0` (EU
  citizens) the salary is still parsed, but nothing is flagged.

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
- Alert jobs that match **no** active filter's keywords: originally not stored; since 2026-10-18
  they are stored for review as `needs_attention` / `alert_review` (§12c). Their message counts as
  `processed` either way.

---

## 6. MCP server tools (`mcp_server/server.py`)

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

## 12b. Additions 2026-10-16 (user requests)

**Document file names.** PDFs are named `<Name>_<Job_title>_<Document>.pdf`:
- the name is the first and last word of `personal.name` (since 2026-10-22, §12f) and the title
  comes from the job; gender tags are dropped,
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

---

## 12c. Additions 2026-10-18 (user requests)

**Runs started from the UI.** "Generate now", "Evaluate now" and "Run now" had silently done
nothing: `spawn(..., {detached: true})` starts PowerShell without a console, and it exits at once.
`runNow` (`ui/src/lib/server/files.ts`) now starts `run.ps1` via `cmd /c start "" /min pwsh
-WindowStyle Hidden …`. The run gets its own hidden console, so it survives a UI restart and
Ctrl+C.

**Telegram notifications** (`core/notify.py`). `run_message` depends on the trigger:
- `docs`: "✍️ Requested documents: N written", one line per job (documents, fit, link), and the
  requested jobs still waiting;
- `single`: the job's fit and decision;
- `evaluate`: "🧮 Scored N waiting jobs …";
- scheduled/manual: the summary line, the new shortlisted jobs without documents and
  "📄 Documents ready".

All runs also list needs_attention jobs, with alert-review jobs as one 📥 line, plus source and
run problems. Runs the user starts that can't start send "⏸ … couldn't start". Settings
`notify_run_summary`, `notify_docs_ready`, `notify_evaluated`, `notify_attention` and
`notify_failures` (migration 011) switch each kind on or off; `telegram_enabled` stays the master
switch.

**Where to apply** (`jobs.apply_url`, migration 011; `core/manual.set_apply_target`):
- The value is a link, or an email address (→ `apply_email`, `apply_method = email`).
- It is set in "+ Add a job", on the job page, or with `cli.py apply-to JOB TARGET`.
- If it is empty, it is taken from the fetched page's "Bewerben/Apply" link, the SmartRecruiters
  `applyUrl`, or a link/email next to "bewerben / apply / Bewerbung / Unterlagen" in the posting
  text (`apply_target_from_text`).
- The apply kit opens `apply_url` if set, and an evaluation never drops an existing `apply_email`.

**Scores for every job:**
- `evaluate_job` also scores jobs that have no fit score but another status (documents requested
  before evaluation, re-evaluation). It stores the score, notes and project ideas and keeps the
  status; history note `scored: fit N`.
- The writer scores an unscored job before tailoring it.
- **Re-evaluate** (job page, `cli.py reevaluate`) clears the score and runs the single-job run. A
  skipped job goes back to `new` (and is screened again); other statuses keep their status and
  documents.
- **Score waiting jobs** (Jobs page, `run.ps1 -Trigger evaluate`) evaluates up to 60 `new` jobs
  without searching, then runs the normal write stage. It is a quick trigger: no time guard.

**Email alerts, fixed:**
- The per-source `limit` (10 per filter) dropped alert jobs, and a processed mail is never read
  again. Now `limit` is ignored for the user's own mails.
- LinkedIn's "Apply with resume & profile" / "Apply now" / "N company alumni" lines shifted the
  fields (title = company); they are now noise.
- `keyword_match` ignores hyphen/space variants: "Full Stack Developer" matches "Full-Stack" and
  "Fullstack", and "Softwareentwickler" matches "Software-Entwickler". A match must start at a word
  boundary, so "Go Developer" doesn't match "Django".
- Alert jobs that match no active filter (newer than the filters' max age) are no longer dropped
  (this replaces the 2026-10-15 decision). `search.store_for_review` stores them as
  `needs_attention` / `alert_review`; they are not evaluated, so no tokens are used.
- On `/attention` they get their own section with bulk actions: evaluate in the next run, evaluate
  now, or not interested. They are counted separately from "Needs you" (📥 badge).
- On 2026-10-18 the last 8 days of alert mails were re-read once (read-only) to recover the dropped
  jobs.

**Favourites:** `jobs.favorite` (migration 011). ☆/★ in the Jobs list and on the job page; the
"★ Favourites" filter is `?fav=1`.

**Job boards** (`/boards`, migration 012 `job_boards`): bookmarks of boards and saved searches the
runs don't cover, with name, link, note and when each was last opened (`/boards/<id>/open`
redirects). One-click suggestions for German boards. JobHunter never fetches these links.

**Statistics** (`/stats`, daily = last 30 days, monthly = last 12 months):
- stat tiles;
- "Your pipeline": documents ready, applied, interview/offer, rejected/withdrawn (stacked
  columns), from `status_history`;
- "Every status": small multiples, one column chart per status, each with its own scale (found,
  scored, shortlisted, skipped, not interested, flagged, alert review, documents ready, applied,
  interview, offer, rejected, withdrawn), plus one combined table;
- jobs per status right now.

The charts are hand-drawn SVG (`ui/src/lib/TimeChart.svelte`) with a hover tooltip, legend and
table view. They use the dataviz reference palette (`--series-1…4`), validated in light and dark
mode.

**Automatic clean-up** (setting `job_retention_days`, 0 = off; migration 013):
- `jobs.purge_old_jobs` runs at the start of scheduled/manual runs.
- It deletes jobs untouched for that many days that the user never acted on: status new, skipped,
  shortlisted or needs_attention, with no application/documents, no documents request, and no ★.
- Their dedup keys go to `deleted_jobs`, so `find_seen` still reports them as seen (R8). Adding
  one by hand removes its tombstone.
- Settings shows how many jobs the current value would delete.

**Tests:** `tests/README.md` lists what each test file covers and the checks still to do by hand.

**CV headline:** `<role> | B.Sc. Computer Engineering`. The role follows the posting's role family
where the profile backs it (skill, "Tailor one job" → CV), otherwise "Softwareentwickler".

---

## 12d. Additions 2026-10-19 (user requests)

**Follow-up reminders** (`core/followups.py`, migration 014):
- An application in status `applied` gets one Telegram reminder after `followup_after_days` (14)
  and one after `followup_no_response_days` (42) suggesting rejected/withdrawn. 0 = off;
  `notify_followups` switches the messages. The status is never changed automatically.
- The applied date is `applications.applied_at`, else the first history row to `applied`.
- `run.ps1` runs `cli.py followups --notify` before scheduled/manual runs, so reminders also go
  out when the time guard refuses the run. Each reminder is recorded
  (`applications.followup_reminded_at` / `no_response_reminded_at`) only after Telegram accepted it.
- Job page (applied jobs): a **Follow-up** panel with a ready text (`cli.py followup-text`,
  German/English by the application language; title, company, date and name only, R5) and
  **I followed up** (`followed_up_at`, history note "followed up"). JobHunter never sends it (R1).

**Applications** (`/applications`): every job the user applied to, with a date filter and the
follow-up state. **CSV (Excel)** (semicolons, UTF-8 BOM) and a printable German **Nachweis der
Eigenbemühungen** (`/applications/print`: date, employer, job, place, how applied, where found,
outcome) as proof of one's own job search for the Agentur für Arbeit / Jobcenter.
`ui/src/lib/server/applications.ts`.

**Profile editor** (`/profile`, `ui/src/lib/server/profile.ts`):
- Motivation per category (one field per active filter name). Saving rewrites only the
  top-level `motivation:` block; unchanged entries keep their original lines. It is refused if
  anything else in the file would change.
- The whole file as YAML.
- Every save is checked by `cli.py check-profile` (core/profile.py) first; the previous file goes
  to `profile/backups/` (last 20).

---

## 12e. Additions 2026-10-21 (user requests)

**Status `feedback`**, shown as "Feedback received" (`ui/src/lib/format.ts` `LABELS`): the employer
replied after the application, but not with an interview. User-only, between `applied` and
`interview` (`core/models.py`; no migration, statuses are plain text). Set it from the job page's
status dropdown; the note field holds what they said.
- Follow-up reminders only cover `applied`, so they stop. The Applications list, CSV and the
  Nachweis include it ("Rückmeldung erhalten").
- Statistics: a "Feedback received" tile, its own step in "Your pipeline", a small chart under
  "Every status" and a "Right now" count. The pipeline now has 5 series: `--series-5` (magenta) is
  slot 5 of the dataviz reference palette; in pipeline order (docs, applied, feedback, interview,
  rejected = slots 1–5) it passes the palette validator in light and dark mode.

**Mobile layout and the reverse tunnel:** see `ui/CLAUDE.md`.

## 12f. Additions 2026-10-22 (user requests)

**CV only by default.** Setting `default_documents` (migration 015): `cv` (default) or `both`.
Runs write only the CV unless the user picks per job (`docs_requested` = cv | letter | both, which
always wins). `core/jobs.documents_to_write` decides; `list_jobs(for_documents)` and `get_job`
return it as `documents`, and `render_documents` refuses a letter the job doesn't ask for. The
email draft then attaches the CV only (subject "Bewerbung als <title>"). In the UI the job page's
document selector preselects the setting, and the list's "Write docs" button uses it.

**A render replaces only what it writes** (user request 2026-10-22). "Cover letter only" after a CV
adds the letter and keeps the CV (and its content and inferred facts in `content.json`); "CV only"
keeps an existing letter; "CV + cover letter" writes both new. Only a render in the other language
removes the old CV/letter, so a job never mixes a German CV with an English letter.

**Motivationsschreiben** (migration 016 `applications.motivation_path`): a third document, written
**only** when the user picks "Motivationsschreiben" on the job page (`docs_requested = motivation`).
- `templates/{motivation_de,motivation_en}.typ` over `templates/lib/motivation.typ`; examples in
  `templates/examples/motivation_*.json`. Letterhead, title, a subtitle naming role and company,
  prose, place/date, typed name. 1–2 pages.
- `docs.render_motivation` checks: schema, 4–9 paragraphs, no cliché opener, project links,
  visa wording, inferred facts (R5/R9; they join the others in `content.json` for approval).
- It replaces only an earlier Motivationsschreiben; CV and letter stay. A later CV/letter render
  keeps it. `render_documents` refuses `motivation_content` unless the job asks for it.
- File names `…_Motivationsschreiben.pdf` / `…_Motivation_Letter.pdf`; the email draft, apply kit,
  Telegram and the job page list it.

**File names: first and last name only.** `document_filename` uses the first and the last word of
`personal.name` ("Max Peter Mustermann" → `Max_Mustermann_…`). Existing files keep their names
until they are written again.

**Where to apply: link, email and postal address together** (migration 016 `jobs.apply_address`).
- `apply_target_from_text` returns the link *and* the email when the posting names both; adding a
  job or its full posting fills in whichever is still empty. Postal addresses are entered by hand.
- `manual.set_apply_places` (`cli.py apply-places JOB --text-file <json>`) saves all three; an
  empty field clears that one. An email sets `apply_method = email` (email draft); clearing it falls
  back to `portal` (link left) or `unknown`.
- Job page: "Where to apply" shows each one found (Apply here ↗, email with copy, postal address
  with copy) and an Edit form with the three fields.

---

## 15. Seed defaults (`seed-filters`): notes

The defaults assume a user who is open to relocating anywhere in Germany (so on-site and hybrid
roles are wanted too) and speaks German well enough for German-language postings and documents.
The user's actual situation lives in `profile.yaml` (`personal.address`, `languages[]`,
`preferences.notes`); adjust the filters in the UI to match.

Exclude keywords for all: `Freelance`, `Freiberuflich`, `Selbstständig`, `Senior Principal`.
For the BA source, map `full_time` to `arbeitszeit=vz` (plus `ho` when remote is wanted). BA
treats the `arbeitszeit` list as OR, so `ho` is only added when remote is wanted and on-site is
not; otherwise it would only widen the results.
All filters stay editable in the UI (`/filters`).

---

## 16. Shareable setup (2026-10-25, user request)

The project owner's own setup (Germany, Yahoo for drafts and alerts, Claude Code) stays the
default, but nothing user-specific is assumed any more. Migration 018 adds the settings below.

**`cli.py setup`** (`core/setup.py`): a guided, re-runnable wizard. It checks the tools, creates
`.env` and `profile/profile.yaml` from the examples, then asks: AI provider and models, drafts
mailbox, job-alert mailbox (the drafts one, another one, or none), Telegram, work permit, and the
first search filters (the IT starter set, or the user's own `Name: title, title` lines). Secrets
go to `.env` (hidden input, never printed); everything else goes to `settings`. Enter keeps the
current value.

**Work permit** (`work_permit_checks`, default `1`): `search._screen` runs the §5a checks only
when it is on. The MCP tool `check_work_authorization` returns no match when it is off, and the
job page hides "Flag: work authorization". Visa questions on forms are still left to the user.

**Mail** (`core/mail_config.py`): `PROVIDERS` holds the presets (yahoo, gmail, gmx, webde,
t-online, icloud). Outlook.com is left out because it no longer accepts app passwords over IMAP.
Host order: `<ROLE>_IMAP_HOST`, then `<ROLE>_MAIL_PROVIDER`, then the address domain
(`guess_host`), then Yahoo for SEND (an error for ALERTS). Both accounts are optional
(`configured()`): without SEND, `save_email_draft` returns `saved_to: null` with a note instead of
failing; with no account at all, `email_alerts` finds nothing. The Drafts fallback names include
`Entwürfe` (GMX, web.de, T-Online).

**Other LLM providers** (`core/agent.py`):
- `.env`: `LLM_PROVIDER` (`claude-code` default | groq | openai | openrouter | mistral | ollama |
  custom), `LLM_API_KEY`, and `LLM_BASE_URL` (custom, or to override a preset).
- Settings `llm_model_filter` / `llm_model_writer` hold the model ids. Setup lists them from the
  provider's `GET /models`; they are never hard-coded because they change too often.
  `model_filter` / `model_writer` stay the Claude Code models.
- `cli.py agent --trigger T --stage S [--job N]` runs one stage. It connects to the jobhunter MCP
  server as an MCP client (same tools, same guards) and uses the job-hunt `SKILL.md` as the system
  prompt.
- It calls `/chat/completions` with tools in a loop, up to 200 turns. On 429/5xx it waits
  (`Retry-After`) and retries.
- `read_file` replaces Claude's `Read` and only opens `templates/` and `.claude/skills/`.
- Tool results are capped at 30k characters, and the oldest ones are blanked once the
  conversation passes `LLM_CONTEXT_CHARS` (default 120k).
- The log gets tool names and sizes only, never tool output (R4).
- `run.ps1` / `run.sh` ask `cli.py llm-provider` and pick `claude -p` or the agent per stage;
  everything else (check-run, notify-failure) is unchanged.
- Limits: apply assist still needs Claude in Chrome. Open models invent facts more easily; the
  code checks (R8, R9, docs.py, drafts only) still apply, and the README warns the user to read
  every document.

**Seed filters:** `seed_default_filters(conn, groups)` takes the user's own groups;
`DEFAULT_FILTERS` is now the "IT starter set".

## 16a. Target countries, remote boards, required Telegram (2026-10-25, user request)

The project is shared with people outside Germany (USA, UK, Canada, Africa, remote, …).

**Countries** (`core/countries.py`, migration 019):
- Keys are python-jobspy's country names (`usa`, `uk`, `south africa`, …) plus `remote` (remote
  jobs in any country) and `worldwide` (any location, incl. on-site abroad). `parse()` accepts
  aliases ("United States", "US", "Deutschland").
- The setting `search_countries` (JSON list, default `["germany"]`, so existing installs don't
  change) is the default for every filter. `search_filters.countries` (non-empty) replaces it for
  that filter. Both are editable in the UI; `cli.py setup` asks for the global list.
- `run_search` resolves the filter's countries first, then skips every source that doesn't cover
  them (`search.covers`, logged, not an error; listed as `not_covered` by `search_jobs`):
  - adapter `countries` = the targets it covers (`ba_jobsuche`, `arbeitnow`: `{"germany"}`;
    None = all);
  - adapter `remote_only` (`himalayas`, `jobicy`): skipped when the filter doesn't accept remote.
- jobspy runs per country: that country's Indeed site, Glassdoor only where it has one
  (`GLASSDOOR`), and LinkedIn "Worldwide" for `remote`/`worldwide` (`is_remote` for remote). The
  per-site limit is shared between the countries.
- §5a: the Blue Card threshold applies only with Germany in `search_countries`. The
  work-authorization phrases now include US/UK/Canada wording ("will not sponsor", "US citizens
  only", "authorized to work … without sponsorship").
- The apply kit's default language for a job with unknown posting language is German only with
  Germany as a target, else English.

**Remote boards** (official APIs, terms: name the board as the source, keep its apply link, never
pass the jobs on to other boards; JobHunter is for personal use):
- `himalayas`: search endpoint, `q` = up to 3 keywords, `country=<ISO-2>` per country target,
  `worldwide=true` for `remote`/`worldwide`, `sort=recent`, 2 pages of 20. Only jobs from the last
  **7 days** (user, 2026-10-25), or fewer per `max_age_days`. Optional `HIMALAYAS_API_KEY` in .env
  (Bearer); without it the shared public allowance.
- `jobicy`: one feed of the last 7 days (≤ 3 pages of 200), matched to every filter locally:
  keywords, then `countries.geo_matches` (country, region such as Europe/EMEA/LATAM, or Anywhere).
- Both go through `FeedCache` (`core/sources/base.py`): each URL is fetched at most once every
  **6 hours** (user decision; `data/cache/<source>/`), however often runs start.

**Telegram is required** in `cli.py setup`: it checks the token (`getMe`), waits until the user has
messaged the bot, finds the chat id (`getUpdates`), and only continues after a test message went
through (`notify.send_with`). A working saved bot can be kept. Notifications themselves are
unchanged (the `telegram_enabled` switch still exists).

## 16b. Deleting a job (2026-10-25, user request)

🗑 on the Jobs list and the job page. The first click only asks ("Delete job?" / on the job page
with the document count and a note when it was applied); "Yes, delete" sends `confirm=yes`,
which the server actions require. `db.deleteJob` stores the dedup keys in `deleted_jobs` (so no run
adds the job again, R8) and deletes the row; the application and `status_history` go with it
(ON DELETE CASCADE). `files.deleteJobFiles` then removes `output/<id>/`. Email drafts already in the
mailbox are not touched.
