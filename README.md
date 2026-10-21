# JobHunter

A local job-search assistant for the German market, driven by **Claude Code** on a Claude Pro
subscription (no API key). Twice a day it searches job boards and your job-alert emails, scores
every new posting against your profile, writes a tailored **Lebenslauf + Anschreiben**
(DIN 5008) or **CV + cover letter**, and reports to Telegram. A local web UI is where you
review, adjust and apply. **It never submits an application — you always do.**

![The Jobs page: every found posting with its fit score, status and quick actions](docs/jobhunter.jpeg)

## What it does

- **Finds jobs:**
  - Bundesagentur für Arbeit (official API), Arbeitnow, and Indeed / LinkedIn / Glassdoor (via
    python-jobspy);
  - your **LinkedIn and Instaffo job-alert emails** (read-only IMAP: nothing is marked as read,
    no login to the boards);
  - any link you paste. Public pages, including SmartRecruiters, softgarden and SuccessFactors
    career sites, are read automatically.
- **Never handles a job twice:** URL canonicalisation plus a company/title/city fingerprint.
- **Screens deterministically:** the salary is compared with the EU Blue Card threshold, and
  demands such as "unrestricted work authorization" are flagged for you to decide.
- **Two models per run:**
  - *Haiku* scores the fit (0–100), classifies the job and suggests small projects that would
    close your gaps;
  - *Sonnet* writes the documents for jobs above your threshold, or any job you pick.
- **Truthful documents:** facts come only from your `profile.yaml`. Anything merely *implied*
  must be listed and approved by you. Style rules are enforced in code: no clichéd openers, 4–5
  paragraphs, the start date in the closing paragraph, links for every project mentioned.
- **Files ready to upload:** Typst PDFs named like
  `Max_Mustermann_Backend_Developer_Lebenslauf.pdf`.
- **Web UI** (SvelteKit), also usable from your phone over Wi-Fi with one-time pairing codes:
  - jobs table with sorting, filters and pages;
  - job pages with fit notes, PDFs and interview prep;
  - an **Apply kit** with copy buttons and a prompt for the Claude browser extension that never
    clicks submit;
  - search filters and run history;
  - an **Applications** list, exportable as CSV or as a printable German record of your
    applications (Nachweis der Eigenbemühungen) for the Agentur für Arbeit / Jobcenter;
  - a **profile editor**, including your motivation per job category.
- **Follow-up reminders:** a Telegram message when an application has had no reply for 14 days,
  with a ready follow-up text, and again after 6 weeks.
- **Email drafts** (never sent) with the PDFs attached, for jobs that apply by email.

## How it works

```
Task Scheduler ─► run.ps1 ─► claude -p (Haiku: search + score) ─► claude -p (Sonnet: documents)
                                   │                                    │
                                   └──── MCP server (Python, core/) ◄───┘
                                              │
                         SQLite (data/) · PDFs (output/) · Telegram · IMAP drafts
                                              │
                                    SvelteKit UI (localhost)
```

The full design, rules and build history are in [CLAUDE.md](CLAUDE.md), which is also the
instruction file Claude Code reads.

## Privacy

Everything runs on your PC. These are gitignored and never leave it:
- your profile (`profile/`);
- the database (`data/`);
- the generated documents (`output/`);
- the logs (`logs/`);
- all secrets (`.env`: mail app passwords, Telegram token).

Claude only sees what the MCP tools hand it: no shell, no web access, no other connectors in
scheduled runs.

## Status

| Phase | What | State |
|-------|------|-------|
| 1 | Foundation: DB, migrations, models, filters, CLI | ✅ |
| 2 | Job sources + dedup + screening (Blue Card salary, work authorization) | ✅ |
| 3 | MCP server | ✅ (document rendering and Telegram are wired in phases 4/5) |
| 4 | Documents (Typst): DE/EN CV, DIN 5008 Anschreiben, EN cover letter | ✅ |
| 5 | Scheduled workflow + Telegram | ✅ |
| 6 | Web UI | ✅ |
| 7 | Mail drafts (Yahoo via IMAP) | ✅ |
| 7a | Two-model runs, letter rules, documents on request, sortable table | ✅ |
| 8 | Apply assist | ✅ |
| 9 | Job-alert emails (LinkedIn, Instaffo; StepStone/XING prepared) | ✅ |
| + | Add jobs by link or pasted text, full postings for alert jobs, descriptive PDF names | ✅ |

## Requirements (Windows)

- Python 3.12 and [uv](https://docs.astral.sh/uv/):
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- [Claude Code](https://claude.com/claude-code), logged in with your Pro subscription.
  Do **not** set `ANTHROPIC_API_KEY`.
- Git.
- Later phases: Node LTS (web UI).

Run everything on Windows itself, not in WSL: the scheduled task, the Python core and the web
UI all share one SQLite file, and SQLite locking is unreliable across the WSL/Windows boundary.

## Setup

```powershell
git clone https://github.com/lenoben/jobhunt.git jobhunter
cd jobhunter
uv sync                                   # creates .venv and installs dependencies
Copy-Item .env.example .env               # fill in later phases' secrets
New-Item -ItemType Directory -Force profile
Copy-Item profile.example.yaml profile/profile.yaml   # then edit it with your data
uv run python cli.py init-db              # creates data/jobhunter.db
uv run python cli.py seed-filters         # inserts the default search filters
```

Then fill in `email` in `profile/profile.yaml` (it has a `<YOUR_ADDRESS>@myyahoo.com` placeholder).

### Mail settings in `.env` (two accounts)

| Account | Used for | Access |
|---------|----------|--------|
| **SEND** (`SEND_*`) | Application emails, saved as **drafts** (never sent) | creates drafts only |
| **ALERTS** (`ALERTS_*`) | Reading LinkedIn/StepStone/XING job-alert emails (planned source, Phase 9) | read-only: no drafts, no sending, nothing marked as read |

Both are generic IMAP over SSL with app passwords, so any provider works. SEND defaults to Yahoo.
For ALERTS, set the host yourself (e.g. `imap.mail.yahoo.com`, `imap.gmail.com`). If you leave
`ALERTS_MAIL_ADDRESS`/`ALERTS_MAIL_APP_PASSWORD` empty, alerts are read from the SEND account,
still read-only.

**Create a Yahoo app password** (your normal Yahoo password never goes into this project):
1. Sign in at <https://login.yahoo.com/account/security>.
2. Open **Generate app password** (also called "App passwords"). If it isn't offered, turn on
   two-step verification on the same page first.
3. Enter a name such as `JobHunter` and click **Generate**.
4. Copy the 16-character password into `SEND_MAIL_APP_PASSWORD` (or `ALERTS_MAIL_APP_PASSWORD`)
   in `.env`. Yahoo shows it only once. If you lose it, delete it and create a new one. Use one
   app password per account.

| Key | Yahoo value |
|-----|-------------|
| `SEND_MAIL_ADDRESS` / `ALERTS_MAIL_ADDRESS` | your address, e.g. `you@myyahoo.com` |
| `SEND_MAIL_APP_PASSWORD` / `ALERTS_MAIL_APP_PASSWORD` | the app password from above |
| `SEND_IMAP_HOST` / `ALERTS_IMAP_HOST` | `imap.mail.yahoo.com` |
| `SEND_IMAP_PORT` / `ALERTS_IMAP_PORT` | `993` |

Test with `uv run python cli.py mail-test` (SEND account), which logs in and shows the folders and
the Drafts folder. `mail-test --create` saves one draft with the subject `JobHunter test` to your
own address. The Drafts folder is the one with the IMAP `\Drafts` special-use flag; if no folder
has the flag, a folder named `Draft` (Yahoo's name) or `Drafts` is used.
`mail-test --account alerts` only checks the ALERTS login and lists its folders.

## CLI

| Command | Does |
|---------|------|
| `init-db` | Creates `data/jobhunter.db` (WAL mode) and applies pending migrations from `core/migrations/` |
| `seed-filters` | Inserts the default search filters (skips ones that already exist by name) and lists them |
| `filters` | Lists all search filters |
| `search --filter N [--source S] [--limit 20] [--dry-run]` | Runs one filter against the sources (`ba_jobsuche`, `arbeitnow`, `jobspy`), drops jobs already seen, screens salary and work-authorization wording, stores new jobs. `--dry-run` stores nothing. |
| `telegram-setup` / `telegram-test` | Print your chat id after you messaged the bot / send a test message |
| `notify-failure [--reason R] [--log L]` | Used by `run.ps1`: marks open runs as failed and sends "🛑 Run failed" |
| `check-run --since "YYYY-MM-DD HH:MM:SS"` | Used by `run.ps1`: exit 1 if a run started since then never finished |
| `add-job --url URL [--text-file F] [--title T] [--company C]` | Add a job by link (public pages are read automatically; LinkedIn/Instaffo need the pasted text). Screened like any other job |
| `update-posting JOB --text-file F` | Add/replace a job's full posting (e.g. one from an alert email); the job is screened and evaluated again |
| `rename-documents` | Rename old `cv.pdf`/`anschreiben.pdf` files to `<Name>_<Job title>_<Document>.pdf` |
| `render-test` | Renders CV + letter in German and English from `templates/examples/` into `output/_render-test/` and checks the page limits (CV ≤ 2, letter = 1) |
| `mail-test [--account send\|alerts] [--create [--job N]]` | Checks the IMAP login. SEND (default): finds the Drafts folder; with `--create`, saves a `JobHunter test` draft to **your own** address. With `--job N`, that job's CV and letter are attached. Afterwards it checks, read-only, that the draft is in Drafts with exactly those attachments and not in Sent. ALERTS: login and folder list only. Never sends. |

Run the tests with `uv run pytest`.

## MCP server

`.mcp.json` registers the `jobhunter` server for Claude Code (`uv run python -m mcp_server.server`).
The first time you open Claude Code in this folder it asks whether to trust the project's MCP
server; say yes. Check it with `claude mcp list`, which should show `jobhunter … ✔ Connected`.
`uv` must be on your PATH: open a new terminal after installing uv.

Tools: `start_run`, `get_active_filters`, `get_settings`, `search_jobs`, `is_seen`, `get_job`,
`get_profile`, `evaluate_job`, `render_documents`, `save_application`, `flag_attention`,
`save_email_draft` (draft only, never sends), `finish_run`. See CLAUDE.md §6.

## Documents

Typst templates in `templates/` (no LaTeX needed; the `typst` Python package compiles them). The
German letter follows DIN 5008 Form B. Claude only writes the content as JSON (schema = the files
in `templates/examples/`), and `output/<job_id>/` gets `cv.pdf` plus `anschreiben.pdf` or
`cover_letter.pdf`, along with `content.json` and `notes.md`.

If Claude adds something your profile implies but doesn't state (e.g. a closely related tool),
it has to list it with its reason. The job then shows up under *needs attention*
(`inferred_facts`) until you approve it, and no email draft is made before that.

## Web UI

```powershell
cd ui
npm install          # once
npm run build        # once, and after updates
npm start            # http://localhost:5173 (local only)
```

`npm run dev` also works while developing. The UI has these pages:
- **+ Add a job:** paste a link, plus the full posting if the page needs a login. With *Evaluate
  now*, Haiku scores it right away, and Sonnet writes the documents if it meets your threshold.
- **Jobs:** filter and search; click a column header to sort (click again to reverse, e.g. by
  fit score); 25/50/100 per page. Row buttons: **Apply anyway** for skipped jobs, **Write docs**
  for jobs without documents, and ✕ **Not interested**. While requested documents are waiting,
  a **Generate now** button writes them right away instead of in the next scheduled run.
- **Job page:** full posting, fit notes, **project suggestions** for the gaps, PDFs, `notes.md`
  and interview prep, a status dropdown with a note, **Mark as applied**, and the history. Under
  **Full posting** you can paste the complete ad (alert emails only contain the title), then
  **Save & evaluate now**. You can
  request **CV only, cover letter only, or both**, for the next run or **Generate now**.
- **Needs you:** approve or reject inferred facts, and resolve flagged jobs.
- **Filters:** create, edit, switch on/off and delete.
- **Runs:** the run history.
- **Settings:** limits, Telegram on/off, Blue Card threshold, and **Run now**.

<p>
  <img src="docs/jobhunter_3.jpeg" width="49%" alt="A job page: status, documents to download or write again, where to apply, fit notes and the Apply kit">
  <img src="docs/jobhunter_2.jpeg" width="49%" alt="Statistics: found, scored, documents, applied and interviews over 30 days, the pipeline per day, and one chart per status">
</p>

*Left: a job page with its fit notes, documents and Apply kit. Right: Statistics, your pipeline
per day and one chart per status.*

**Apply kit** (on each job with documents) has:
- the application link and the PDF paths to upload;
- every form value with a **Copy** button (name, first/last name, email, phone, address, start
  date, hours, salary, links, short motivation);
- a ready-made **prompt for the Claude browser extension**: it fills the form, uploads the files,
  leaves work-authorization/visa questions empty, and never submits;
- **Flag: work authorization**, for forms that demand it.

In Claude Code you can also say "help me apply to job 42", which uses the `apply-assist` skill.
You always log in, solve CAPTCHAs, answer work-permit questions and click submit yourself.
`cli.py apply-kit N` prints the same prompt.

The UI rejects requests from other websites. By default it only answers on this PC.

### Phones and tablets on the PC's Mobile Hotspot
1. In `.env`, set `UI_LAN=1`, `UI_LAN_SUBNETS=192.168.137.0/24` and a `UI_SESSION_SECRET`
   (see `.env.example`). Then restart the UI (`npm start`).
2. Turn on **Windows Settings → Network → Mobile hotspot** and connect the phone to it.
3. On the PC, open **Settings → Pair a device** to get a 6-digit code. It is valid for 10 minutes
   and works once.
4. On the phone, open `http://192.168.137.1:5173/` and enter the code. The phone stays signed in
   for a year.

To use your normal Wi-Fi as well, add its range to `UI_LAN_SUBNETS`, e.g.
`192.168.137.0/24,192.168.0.0/24`, and open `http://<PC address>:5173/` (here
`http://192.168.0.157:5173/`). Do this only on a network you trust: the UI uses plain HTTP.
Devices on networks not listed are always refused. To sign out every device, change
`UI_SESSION_SECRET`.

## Scheduled runs and Telegram

1. **Telegram:**
   - Create a bot with [@BotFather](https://t.me/BotFather) and put the token into
     `TELEGRAM_BOT_TOKEN`.
   - Send the bot any message, then run `uv run python cli.py telegram-setup` and put the printed
     id into `TELEGRAM_CHAT_ID`.
   - Check it with `cli.py telegram-test`.
2. **Manual run:** `.\run.ps1 -Trigger manual`. `.\run.ps1 -Trigger docs` writes only the requested documents. Claude works headless with only the JobHunter
   tools. Logs go to `logs/run_<time>_<trigger>.log`.
3. **Schedule:** `.\setup-task.ps1` registers the task **JobHunter**. It runs daily at 08:00 and
   18:00, catches up after the PC was off, wakes the PC, needs network, and stops after 2 h at
   most. It runs only while you're logged on, so no password is stored. Run the script again
   after changes; it updates the task.

Each run has two stages:
- **Haiku** (setting `model_filter`) searches, filters and scores.
- **Sonnet** (`model_writer`) writes CVs and cover letters.

Documents are written automatically for jobs with fit ≥ `min_fit_for_documents` (60), and for
any job where you clicked *Apply anyway* or *Write docs*. All three settings are editable in the
UI.

A run is refused if one is still running or the last one finished less than
`min_hours_between_runs` (4 h) ago. *Generate now* runs don't wait for that gap. Each run evaluates at most `max_evaluated_per_run` (30) new
jobs and tailors at most `max_tailored_per_run` (5); the rest carry over. After each run you get
one Telegram message with the counts, failed sources and the jobs that need you.

## Job sources

| Key | Boards | Notes |
|-----|--------|-------|
| `ba_jobsuche` | Bundesagentur für Arbeit | Official API. Germany only. Salary is rarely given. |
| `arbeitnow` | Arbeitnow | Public API; one shared feed, matched to filters locally. Only jobs from the German site (arbeitnow.com) are kept; .co.uk/.fr/.ch/.nl and foreign locations are dropped. |
| `email_alerts` | Your LinkedIn job-alert emails (StepStone/XING prepared) | Reads the ALERTS mailbox **read-only**: nothing is marked as read, no LinkedIn login, no requests to LinkedIn. Each mail is processed once. Only jobs matching a filter's keywords are stored. Senders and folder are editable in Settings. |
| `jobspy` | Indeed DE, LinkedIn, Glassdoor | Scraped, max 20 per site per run, 3 s between requests. LinkedIn often blocks; that is recorded as an error and the other sites continue. (Google Jobs was removed: it never returned results.) |

Each new job is screened before it is stored:
- **Salary:** converted to gross EUR per year (upper value of a range) and compared to the EU Blue
  Card threshold in the `blue_card_salary_min` setting (45,934.20 € for 2026). Below → *needs
  attention*. No salary → `salary_unknown` (informational only).
- **Work authorization:** ads asking for e.g. *unbefristete Arbeitserlaubnis*,
  *EU-Staatsbürgerschaft* or *no visa sponsorship* → *needs attention*, so you answer those yourself.

## Where things live

| Path | Contents | In git? |
|------|----------|---------|
| `profile/profile.yaml` | Your CV data — the only source for generated documents | no |
| `data/jobhunter.db` | Jobs, applications, filters, runs | no |
| `output/<job_id>/` | Generated PDFs and notes | no |
| `logs/` | One log per run | no |
| `.env` | Telegram token, SEND and ALERTS mail app passwords | no |

## Schema changes

Add a new numbered file such as `core/migrations/002_something.sql`. `init-db` (and every
connection that calls `migrate`) applies files it has not seen yet, recorded in
`schema_migrations`. Never edit a migration that has already been applied.
