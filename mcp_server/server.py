"""JobHunter MCP server (CLAUDE.md §6). Run: uv run python -m mcp_server.server

Thin layer: validates input and calls core/. No raw SQL here. stdout belongs to the MCP stdio
transport, so anything chatty (adapters, jobspy) is redirected to stderr.
"""

from __future__ import annotations

import contextlib
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from core import applications, db, jobs, runs
from core.filters import load_filters
from core.profile import ProfileError, load_profile

server = MCPServer(
    name="jobhunter",
    instructions=(
        "JobHunter: finds German job postings, stores them in SQLite and prepares application "
        "documents. Never submit applications or send email (R1). Call is_seen before working on "
        "any job URL (R8). Only evaluate jobs with status 'new'."
    ),
)

SHORT_DESCRIPTION = 300


@contextlib.contextmanager
def _db():
    """One connection per tool call (tools run in worker threads); known errors become ToolErrors."""
    conn = db.connect()
    try:
        yield conn
    except (ValueError, runs.RunRefused, ProfileError, RuntimeError) as e:
        conn.rollback()
        raise ToolError(str(e)) from None
    finally:
        conn.close()


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


@server.tool()
def start_run(trigger: str = "scheduled") -> dict[str, Any]:
    """Start a job-hunt run. trigger: 'scheduled', 'manual', 'docs' (writer only, for jobs the user
    requested documents for), 'single' (one job) or 'evaluate' (backlog of new jobs, no search); the
    last three are not subject to min_hours_between_runs. Returns {started: true, run_id}, or
    {started: false, reason} if a run is still running or the last one finished less than
    min_hours_between_runs ago — then stop quietly."""
    with _db() as conn:
        try:
            return {"started": True, "run_id": runs.start_run(conn, trigger)}
        except runs.RunRefused as e:
            if trigger in ("docs", "single", "manual", "evaluate"):  # started by the user: tell them on Telegram
                from core import notify
                notify.notify_run_refused(conn, trigger, str(e))
            return {"started": False, "reason": str(e)}


@server.tool()
def get_active_filters() -> list[dict[str, Any]]:
    """All active search filters (keywords, location, work modes, employment types, min_fit_score …)."""
    with _db() as conn:
        return [vars(f).copy() for f in load_filters(conn, active_only=True)]


@server.tool()
def get_settings() -> dict[str, str]:
    """Settings: max_tailored_per_run, min_hours_between_runs, telegram_enabled, ui_base_url,
    blue_card_salary_min, blue_card_salary_year."""
    with _db() as conn:
        return db.get_settings(conn)


@server.tool()
def search_jobs(filter_id: int, sources: list[str] | None = None, limit: int | None = None,
                run_id: int | None = None) -> dict[str, Any]:
    """Run one filter against the job sources, drop already-seen jobs and store only unseen ones.
    New jobs get status 'new', or 'needs_attention' when a screening check hits (salary below the
    Blue Card threshold, work-authorization wording) — do not evaluate those. limit = max postings
    per source (1–50, default: setting search_limit_per_source). Errors and counts go to run_id
    (default: the currently running run). Slow: scraped sources wait ≥3 s between requests."""
    from core.search import run_search
    from core.sources import SOURCES

    if limit is not None and not 1 <= limit <= 50:
        raise ToolError("limit must be between 1 and 50")
    unknown = [s for s in sources or [] if s not in SOURCES]
    if unknown:
        raise ToolError(f"unknown source(s) {', '.join(unknown)}; available: {', '.join(SOURCES)}")
    with _db() as conn:
        limit = limit or int(db.get_settings(conn).get("search_limit_per_source", "10"))
        f = next((x for x in load_filters(conn) if x.id == filter_id), None)
        if f is None:
            raise ValueError(f"no search filter with id {filter_id}")
        run_id = run_id or runs.current_run_id(conn)
        if run_id is not None:
            runs.get_run(conn, run_id)  # validates the id
        with contextlib.redirect_stdout(sys.stderr):
            r = run_search(conn, f, sources=sources, limit=limit, log=_log)
        if run_id is not None:
            runs.add_errors(conn, run_id, [e | {"filter_id": f.id} for e in r.errors])
            runs.add_counts(conn, run_id, found=r.found, new_jobs=len(r.new))
            # one search per source (and per jobspy site), so the summary can say "2 of 6 filters"
            keys = []
            for key in sources or f.sources:
                site_list = getattr(SOURCES.get(key), "sites", None)
                keys += [f"{key}:{s}" for s in site_list] if site_list else [key]
                if site_list:
                    keys.append(key)  # the adapter as a whole can fail too
            runs.add_searches(conn, run_id, keys)
            conn.commit()
        return {
            "filter": f.name,
            "run_id": run_id,
            "found": r.found,
            "duplicates": r.duplicates,
            "too_old": r.too_old,
            "skipped_by_prefilter": len(r.skipped),
            "errors": r.errors,
            "new_jobs": [{
                "id": p.id, "title": p.title, "company": p.company, "location": p.location, "url": p.url,
                "status": p.status, "attention_reason": p.attention_reason,
                "salary_flag": p.salary_flag,
                "short_description": _short(p.description),
            } for p in r.new],
        }


@server.tool()
def is_seen(url: str) -> dict[str, Any]:
    """Whether a job URL is already in the database (after URL canonicalisation).
    Returns {seen: false} or {seen: true, job_id, status}."""
    if not url.strip().lower().startswith(("http://", "https://")):
        raise ToolError("url must start with http:// or https://")
    with _db() as conn:
        return jobs.is_seen(conn, url.strip())


@server.tool()
def list_jobs(status: str, limit: int = 50, for_documents: bool = False,
              requested_only: bool = False) -> list[dict[str, Any]]:
    """Brief rows (no description) of jobs with one status, e.g. 'new' (to evaluate, newest posting
    first) or 'shortlisted' (highest fit_score first). for_documents=true (writer stage): only the
    shortlisted jobs that get documents — fit_score ≥ min_fit_for_documents, or docs_requested by
    the user, requested ones first. Each row's `documents` ('cv' | 'letter' | 'both' | 'motivation')
    says which to write: the user's choice for that job, else the setting default_documents (CV only
    by default). 'motivation' = only a Motivationsschreiben (motivation_content), never written unasked.
    requested_only=true (with for_documents, "docs" runs): only the jobs the user requested."""
    with _db() as conn:
        rows = jobs.list_jobs(conn, status, limit, for_documents)
        return [r for r in rows if r["docs_requested"]] if requested_only else rows


@server.tool()
def current_run() -> dict[str, Any]:
    """The run that is still open ({run_id} or {run_id: null}). The writer stage continues it."""
    with _db() as conn:
        return {"run_id": runs.current_run_id(conn)}


@server.tool()
def get_job(job_id: int) -> dict[str, Any]:
    """The full job including description, fit notes, its application (if any) and status history.
    `documents` (cv | letter | both | motivation) says which documents to write for it."""
    with _db() as conn:
        job = jobs.get_job(conn, job_id)
        for k in ("user_notes", "user_notes_at"):  # the user's private notes (migration 017), not for runs
            job.pop(k, None)
        f = next((x for x in load_filters(conn) if x.id == job["filter_id"]), None)
        job["filter_name"] = f.name if f else None  # key for profile.motivation (§7 rule 2)
        job["documents"] = jobs.documents_to_write(conn, job["docs_requested"])  # cv | letter | both | motivation
        job["application"] = applications.get_application(conn, job_id)
        job["history"] = jobs.history(conn, job_id)
        return job


@server.tool()
def get_profile() -> dict[str, Any]:
    """The user's parsed profile.yaml — the only source of facts for CVs and letters (R5).
    'warnings' lists gaps or placeholders found while validating it. 'rejected_inferences' are
    statements the user rejected earlier (R9): never use them again, in any job."""
    try:
        profile, warnings = load_profile()
    except ProfileError as e:
        raise ToolError(str(e)) from None
    with _db() as conn:
        rejected = [{"text": r["text"], "basis": r["basis"]} for r in applications.rejected_inferences(conn)]
    return {"profile": profile, "warnings": warnings, "rejected_inferences": rejected}


@server.tool()
def evaluate_job(job_id: int, fit_score: int, fit_notes: str, work_mode: str, employment_type: str,
                 language: str, apply_method: str, decision: str,
                 apply_email: str | None = None,
                 project_suggestions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Store your evaluation of a job with status 'new' (→ shortlisted/skipped), or of a job in another
    status that has no fit_score yet (score, notes and project ideas are stored; the status stays).
    work_mode: remote|hybrid|onsite|unknown. employment_type: full_time|part_time|minijob|
    working_student|internship|contract|freelance|unknown. language (of the posting): de|en.
    apply_method: portal|email|external_ats|unknown (apply_email required for 'email').
    decision: 'skip' or 'shortlist' (shortlist needs fit_score ≥ the filter's min_fit_score).
    fit_notes: Markdown — why it fits, gaps, and 'salary unknown' when salary_flag says so.
    project_suggestions (R11, for gaps): [{title, scope, days, covers}] — small realistic projects
    the user could build; shown in the UI, never put into documents."""
    with _db() as conn:
        status = jobs.evaluate_job(conn, job_id, fit_score, fit_notes, work_mode, employment_type,
                                   language, apply_method, decision, apply_email, project_suggestions)
        return {"job_id": job_id, "status": status}


@server.tool()
def render_documents(job_id: int, doc_language: str, cv_content: dict[str, Any] | None = None,
                     letter_content: dict[str, Any] | None = None,
                     motivation_content: dict[str, Any] | None = None) -> dict[str, Any]:
    """Render the CV and/or cover letter (Typst → PDF) into output/<job_id>/, named
    <Name>_<Job_title>_Lebenslauf|Anschreiben.pdf (de) or …_CV|Cover_Letter.pdf (en).
    doc_language = the posting's language. Give exactly the documents the job's `documents` says
    (list_jobs): its docs_requested, else the setting default_documents — CV only by default.
    documents = 'motivation': give only motivation_content (a Motivationsschreiben, 1–2 pages, 4–9
    paragraphs, no cliché opener, project links as in the letter). It leaves the CV and letter as they are.
    motivation_content {sender{name,street,city,phone,email}, subtitle ("<role> bei <company>"),
    salutation?, body[paragraphs], place, date?, closing?, inferred[]} (templates/examples/motivation_*.json).
    Letter rules checked here: no cliché opener, 4–5 body paragraphs, last paragraph states the
    start date / availability, every profile project named in the letter carries its URL.
    Schemas (see templates/examples/*.json): cv_content {name, headline, summary, contact{address,
    phone, email, links[]}, personal[{label,value}], experience[{from,to,title,org,place,bullets[],
    tech[]}], education[{from,to,title,org,place,details[]}], projects[{name,url,description,
    tech[]}], skills[{group,items[]}], languages[{language,level,note}], certificates[{date,name,
    issuer}], inferred[]}; letter_content {sender{name,street,city,phone,email}, recipient{lines[]},
    place, date?, subject, reference?, salutation, body[paragraphs], closing?, attachments[],
    inferred[]}. Dates MM/YYYY, 'present' for ongoing. The photo comes from profile.yaml (German CVs
    only). R5/R9: list EVERY statement not literally in the profile under `inferred` as
    {text, where, basis}; such documents wait for the user's approval. Errors tell you what to fix
    (e.g. too many pages, visa wording the posting doesn't ask for)."""
    from core import docs

    with _db() as conn:
        job = jobs.get_job(conn, job_id)
        wanted = jobs.documents_to_write(conn, job.get("docs_requested"))
        if wanted == "cv" and (letter_content or not cv_content):
            raise ValueError("CV only for this job (docs_requested or the setting "
                             "default_documents): give cv_content and no letter_content")
        if wanted == "letter" and (cv_content or not letter_content):
            raise ValueError("the user asked for the cover letter only: give letter_content and no cv_content")
        if wanted == "motivation" and (cv_content or letter_content or not motivation_content):
            raise ValueError("the user asked for a Motivationsschreiben only: give motivation_content and nothing else")
        if wanted != "motivation" and motivation_content:
            raise ValueError("a Motivationsschreiben is written only when the user asks for it (documents = 'motivation')")
        try:
            profile = load_profile()[0]
        except ProfileError as e:
            raise ToolError(str(e)) from None
        posting = "\n".join(filter(None, (job["title"], job["description"])))
        if wanted == "motivation":
            return docs.render_motivation(applications.output_dir(job_id), doc_language, motivation_content,
                                          posting_text=posting, rejected=applications.rejected_inferences(conn),
                                          projects=profile.get("projects") or [],
                                          person=(profile.get("personal") or {}).get("name"), job_title=job["title"])
        return docs.render(job_id, doc_language, cv_content, letter_content, posting_text=posting,
                           photo=(profile.get("personal") or {}).get("photo"),
                           rejected=applications.rejected_inferences(conn), projects=profile.get("projects") or [],
                           person=(profile.get("personal") or {}).get("name"), job_title=job["title"])


@server.tool()
def save_application(job_id: int, summary: str, interview_prep: str, method: str) -> dict[str, Any]:
    """After render_documents: record the application (what was emphasised and why, interview
    prep in Markdown, how the user will submit it), write output/<job_id>/notes.md and set the
    job to docs_ready — or to needs_attention (inferred_facts) if the documents contain inferred
    facts, which the user must approve first."""
    with _db() as conn:
        return applications.save_application(conn, job_id, summary, interview_prep, method)


@server.tool()
def flag_attention(job_id: int, reason: str, detail: str) -> dict[str, Any]:
    """Set a job to needs_attention so the user handles it. reason: needs_login|captcha|
    form_unclear|missing_profile_info|german_only_form|source_error|work_authorization|
    below_blue_card_threshold|inferred_facts. detail: one sentence on what the user has to do."""
    if not detail.strip():
        raise ToolError("detail must not be empty")
    with _db() as conn:
        jobs.flag_attention(conn, job_id, reason, detail.strip())
        return {"job_id": job_id, "status": "needs_attention", "reason": reason}


@server.tool()
def save_email_draft(job_id: int, subject: str, body: str) -> dict[str, Any]:
    """Save the application email as a DRAFT in the user's mailbox (to the job's apply_email, with
    the CV and, if written, the letter and Motivationsschreiben attached). Never sends (R1) — the user reviews and sends it."""
    if not subject.strip() or not body.strip():
        raise ToolError("subject and body must not be empty")
    from core import mail_drafts

    with _db() as conn:
        job = jobs.get_job(conn, job_id)
        if not job["apply_email"]:
            raise ValueError(f"job {job_id} has no apply_email")
        app = applications.get_application(conn, job_id)
        if app is None:
            raise ValueError(f"job {job_id} has no application yet; call save_application first")
        if app["inferred_facts"] and not app["inferred_approved_at"]:
            raise ValueError(f"job {job_id} has inferred facts the user hasn't approved yet (R5/R9); no draft")
        cv, letter, _lang = applications.find_documents(job_id)
        files = [p for p in (cv, letter, applications.find_motivation(job_id)) if p]
        result = mail_drafts.create_draft(to=job["apply_email"], subject=subject.strip(), body=body,
                                          attachments=files)
        if not result["confirmed"]:
            raise RuntimeError(f"draft was appended to {result['folder']} but could not be found there")
        applications.mark_email_draft_saved(conn, job_id)
        return {"job_id": job_id, "saved_to": result["folder"], "to": job["apply_email"],
                "attachments": [p.name for p in files], "sent": False}


@server.tool()
def get_apply_kit(job_id: int) -> dict[str, Any]:
    """Apply assist (§13): the application URL, the PDF paths to upload, the form field values
    (name, contact, address, earliest start, hours, salary text, short motivation) and a ready-made
    prompt. For filling forms only — never submit, log in, create accounts or solve CAPTCHAs."""
    from core.apply_kit import build_kit

    try:
        profile = load_profile()[0]
    except ProfileError as e:
        raise ToolError(str(e)) from None
    with _db() as conn:
        return build_kit(conn, job_id, profile)


@server.tool()
def check_work_authorization(text: str) -> dict[str, Any]:
    """Scan text from a live application form/page for demands the user must answer personally
    (§5a: unbefristete/uneingeschränkte Arbeitserlaubnis, EU-Staatsbürgerschaft, EU citizens only,
    no visa sponsorship, …). Returns {match: phrase or null}. On a match: leave those questions
    empty and flag_attention(job_id, 'work_authorization', <phrase>)."""
    from core.checks import check_work_authorization as check

    return {"match": check(text, None)}


@server.tool()
def finish_run(run_id: int, failed_reason: str | None = None) -> dict[str, Any]:
    """Close the run and send the Telegram summary (counts, failed sources, jobs that need the
    user). All counts are taken from the database. Pass failed_reason only if the run could not
    do its work."""
    from core import notify

    with _db() as conn:
        run = runs.finish_run(conn, run_id, failed_reason=failed_reason)
        summary = runs.summary_line(run)
        telegram = notify.notify_run_finished(conn, run, summary)
    return {"run_id": run_id, "status": run["status"], "summary": summary,
            "errors": run["errors"], "telegram": telegram}


def _short(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= SHORT_DESCRIPTION else text[:SHORT_DESCRIPTION].rsplit(" ", 1)[0] + " …"


def main() -> None:
    with db.connect() as conn:  # apply pending migrations once at startup
        db.migrate(conn)
    conn.close()
    server.run("stdio")


if __name__ == "__main__":
    main()
