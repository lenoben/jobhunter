# JobHunter — Project Blueprint

A local, open-source job-search assistant for the German market, driven by Claude Code on a
Claude Pro subscription (no Anthropic API key). It finds jobs, filters and scores them, writes a
tailored CV + cover letter per job, logs everything in SQLite, notifies via Telegram, and shows
everything in a localhost web UI. **Applying is always finished by the human.**

> This file is the source of truth, together with `core/CLAUDE.md` (sources, MCP tools, documents,
> notifications, feature additions) and `ui/CLAUDE.md` (web UI). Read them fully before changing
> those parts.

---

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

## 4. Database schema

Owned by the numbered SQL files in `core/migrations/` (applied by `core/db.py`); read them for tables and columns.

### Job statuses

| Status | Set by | Meaning |
|--------|--------|---------|
| `new` | Claude | Found, not yet evaluated |
| `skipped` | Claude/user | Below fit score, excluded keyword, freelance, duplicate, or "Not interested". The user can still pursue it: **Apply anyway** in the UI → `shortlisted` + `docs_requested` |
| `shortlisted` | Claude/user | Worth applying (fit ≥ the filter's `min_fit_score`) but no documents yet. Documents are written automatically only if `fit_score ≥ min_fit_for_documents` (60, editable), or if the user clicked **Write documents** (`docs_requested`). Otherwise the job waits for the user's decision |
| `docs_ready` | Claude | CV + letter generated, ready for the user to apply |
| `needs_attention` | Claude | Human needed: `needs_login`, `captcha`, `form_unclear`, `missing_profile_info`, `german_only_form`, `source_error`, `work_authorization`, `below_blue_card_threshold` (see §5a), `inferred_facts` (R5/R9, §7), `alert_review` (job-alert job matching no filter, §12c) |
| `applied` | **user only** | User submitted |
| `feedback` | **user only** | Shown as "Feedback received": the employer replied, but not with an interview. Set from the status dropdown; no more follow-up reminders (§12e) |
| `interview`, `offer`, `rejected`, `withdrawn` | **user only** | Pipeline tracking |

Every status change writes a row to `status_history`.

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
   Write the documents the job's `documents` field asks for (the CV only by default, setting
   `default_documents`; the user can pick CV + letter per job) → `render_documents` → `save_application`.
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

## Where the rest lives

- `core/CLAUDE.md`: §5 job sources, dedup, §5a screening, §5b email alerts · §6 MCP server notes ·
  §7 documents and cover-letter rules · §8 notifications · §12b–§12d feature additions ·
  §15 seed-filter notes
- `ui/CLAUDE.md`: §12 web UI
- Folder layout, the DB schema, the MCP tool list and the CLI commands are read from the code
  (`core/migrations/`, `mcp_server/server.py`, `cli.py --help`).
