"""JobHunter dev/manual CLI. Usage: uv run python cli.py <command> [options]"""

from __future__ import annotations

import argparse
import sys

from core import db
from core.filters import load_filters, seed_default_filters


def cmd_init_db(args: argparse.Namespace) -> int:
    path, applied = db.init_db()
    if applied:
        print(f"Database ready at {path}. Applied: {', '.join(applied)}")
    else:
        print(f"Database at {path} is already up to date.")
    return 0


def cmd_seed_filters(args: argparse.Namespace) -> int:
    db.init_db()
    conn = db.connect()
    inserted = seed_default_filters(conn)
    print(f"Inserted {len(inserted)} filter(s)." if inserted else "All default filters already exist.")
    _print_filters(conn)
    conn.close()
    return 0


def cmd_filters(args: argparse.Namespace) -> int:
    conn = db.connect()
    db.migrate(conn)
    _print_filters(conn)
    conn.close()
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    from core.search import prefilter, run_search

    db.init_db()
    conn = db.connect()
    f = next((x for x in load_filters(conn) if x.id == args.filter), None)
    if f is None:
        raise RuntimeError(f"No filter with id {args.filter}. List them with: cli.py filters")
    sources = [args.source] if args.source else None
    mode = "DRY RUN (nothing stored)" if args.dry_run else "storing new jobs"
    print(f"Filter {f.id} '{f.name}' · sources: {', '.join(sources or f.sources)} · limit {args.limit} · {mode}")
    r = run_search(conn, f, sources=sources, limit=args.limit, dry_run=args.dry_run, log=print)
    conn.close()

    print(f"\n{'status':16} {'salary':24} {'source':12} title — company, location")
    for p in r.new + r.skipped:
        flag = p.attention_reason or (p.status if p.status != "new" else "")
        salary = p.salary_flag or ""
        if p.salary_annual_eur:
            salary += f" €{p.salary_annual_eur:,.0f}"
        print(f"{(flag or 'new'):16} {salary:24} {p.source:12} {p.title} — {p.company or '?'}, {p.location or '?'}")
        if p.status == "skipped":
            print(f"{'':16} reason: {prefilter(p, f)}")
        print(f"{'':16} {p.url}")
    print(f"\nFound {r.found} · new {len(r.new)} · skipped {len(r.skipped)} · duplicates {r.duplicates} "
          f"· older than {f.max_age_days} days {r.too_old}" + (" (dry run: not stored)" if args.dry_run else ""))
    for e in r.errors:
        print(f"  error [{e['source']}]: {e['message']}")
    return 0


def cmd_render_test(args: argparse.Namespace) -> int:
    from core import docs

    ok = True
    for r in docs.render_test():
        limits = r["cv_pages"] <= docs.MAX_PAGES["cv"] and r["letter_pages"] == docs.MAX_PAGES["letter"] \
            and r["motivation_pages"] <= docs.MAX_PAGES["motivation"]
        ok &= limits
        print(f"[{r['doc_language']}] CV {r['cv_pages']} page(s) → {r['cv_path']}")
        print(f"     letter {r['letter_pages']} page(s) → {r['letter_path']}")
        print(f"     Motivationsschreiben {r['motivation_pages']} page(s) → {r['motivation_path']}")
    print("Page limits OK (CV ≤ 2, letter = 1, Motivationsschreiben ≤ 2)." if ok else "Page limits exceeded!")
    return 0 if ok else 1


def cmd_mail_test(args: argparse.Namespace) -> int:
    from core import mail_config, mail_drafts

    if args.job and not args.create:
        raise RuntimeError("--job only makes sense with --create")
    if args.create and args.account != "send":
        raise RuntimeError("--create only works with the SEND account; the ALERTS account is read-only")
    cfg = mail_config.load_config(args.account)
    via = "" if cfg.source.lower() == cfg.role else f" (ALERTS_ empty → using {cfg.source} credentials, read-only)"
    print(f"[{cfg.role} account{via}] Logging in as {cfg.address} at {cfg.host}:{cfg.port} …")
    conn = mail_drafts.connect(cfg)
    try:
        folders = mail_drafts.list_folders(conn)
    finally:
        conn.logout()
    for f in folders:
        print(f"  {f.name:30} {' '.join(f.flags)}")
    if args.account == "alerts":
        print("Login OK. The ALERTS account is only ever read (no drafts, no flag changes).")
        return 0
    folder, found_by = mail_drafts.find_drafts_folder(folders)
    print(f"Drafts folder: {folder} (via {found_by})")
    if not args.create:
        print("No draft created (use --create). Nothing is ever sent.")
        return 0
    attachments, subject = [], "JobHunter test"
    if args.job:
        from core.applications import find_documents, find_motivation
        cv, letter, _lang = find_documents(args.job)  # raises a clear error if not rendered yet
        attachments = [p for p in (cv, letter, find_motivation(args.job)) if p]
        subject = f"JobHunter test – job {args.job} documents"
    result = mail_drafts.create_draft(
        to=cfg.address,  # always your own address: a test never addresses an employer
        subject=subject,
        body="Test draft created by JobHunter (cli.py mail-test --create). "
             "It was saved as a draft only and never sent. You can delete it.",
        attachments=attachments,
    )
    status = "confirmed in" if result["confirmed"] else "APPENDED BUT NOT FOUND in"
    print(f"Draft '{subject}' {status} {result['folder']} (Message-ID {result['message_id']}).")

    check = mail_drafts.inspect_message(result["message_id"], cfg)
    print(f"Check (read-only): in Drafts={check['in_drafts']} · \\Draft flag={check['draft_flag']} · "
          f"in Sent={check['in_sent']} · attachments={check['attachments'] or 'none'}")
    expected = [p.name for p in attachments]
    ok = (result["confirmed"] and check["in_drafts"] and not check["in_sent"]
          and sorted(check["attachments"]) == sorted(expected))
    print("OK: draft saved with the expected attachments, nothing sent." if ok else "PROBLEM: see the check above.")
    return 0 if ok else 1


def cmd_telegram_setup(args: argparse.Namespace) -> int:
    from core import notify

    chats = notify.get_chat_ids()
    if not chats:
        print("No messages yet. Send any message to your bot in Telegram, then run this again.")
        return 1
    for c in chats:
        print(f"chat id {c['id']}  ({c['type']}, {c['name']})")
    print("Put the id into TELEGRAM_CHAT_ID in .env.")
    return 0


def cmd_telegram_test(args: argparse.Namespace) -> int:
    from core import notify

    result = notify.send("✅ JobHunter test message — Telegram works.")
    print(f"Telegram: {result}")
    return 0 if result == "sent" else 1


def cmd_notify_failure(args: argparse.Namespace) -> int:
    """Called by run.ps1 when claude exits non-zero or leaves a run open. Never fails itself."""
    from core import notify, runs

    db.init_db()
    conn = db.connect()
    try:
        closed = runs.fail_open_runs(conn, args.reason)
        result = notify.notify_run_failed(conn, args.reason, args.log)
    finally:
        conn.close()
    print(f"Closed run(s) {closed or 'none'} as failed · Telegram: {result}")
    return 0


def cmd_check_run(args: argparse.Namespace) -> int:
    """Exit 1 if a run started since --since (UTC 'YYYY-MM-DD HH:MM:SS') is still marked running."""
    from core import runs

    conn = db.connect()
    try:
        open_ids = runs.still_running_since(conn, args.since)
        last = conn.execute("SELECT id, status, started_at FROM runs WHERE started_at >= ? ORDER BY id DESC LIMIT 1",
                            (args.since,)).fetchone()
    finally:
        conn.close()
    if open_ids:
        print(f"Run(s) {open_ids} never called finish_run.")
        return 1
    print(f"Run {last['id']}: {last['status']}" if last else "No run was started (refused by the time guard or nothing to do).")
    return 0


def cmd_apply_kit(args: argparse.Namespace) -> int:
    """Print the apply kit (§13) for a job: URL, files, field values and the browser prompt."""
    import json

    from core.apply_kit import build_kit
    from core.profile import load_profile

    conn = db.connect()
    try:
        kit = build_kit(conn, args.job, load_profile()[0])
    finally:
        conn.close()
    if args.json:
        print(json.dumps(kit, ensure_ascii=False, indent=2))
    else:
        print(kit["prompt"])
    return 0


def _read_text(path: str | None) -> str | None:
    from pathlib import Path
    return Path(path).read_text(encoding="utf-8") if path else None


def cmd_add_job(args: argparse.Namespace) -> int:
    """Add a job by link (fetched if public) and/or pasted posting text."""
    import json

    from core.manual import ManualJobError, add_manual_job

    db.init_db()
    conn = db.connect()
    try:
        result = add_manual_job(conn, args.url, _read_text(args.text_file), args.title, args.company, args.location,
                                args.apply_to)
    except ManualJobError as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False) if args.json else
          (f"Error: {result['error']}" if "error" in result else
           f"job {result['job_id']} ({'added' if result['created'] else 'existing'}, {result['status']}): {result['note']}"))
    return 1 if "error" in result else 0


def cmd_update_posting(args: argparse.Namespace) -> int:
    """Add/replace a job's full posting text; the job is screened again and set back to 'new'."""
    import json

    from core.manual import ManualJobError, update_posting

    conn = db.connect()
    try:
        result = update_posting(conn, args.job, _read_text(args.text_file) or "")
    except (ManualJobError, ValueError) as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False) if args.json else result)
    return 1 if "error" in result else 0


def cmd_reevaluate(args: argparse.Namespace) -> int:
    """Evaluate a job again with the posting text it already has (back to 'new')."""
    import json

    from core.manual import ManualJobError, reevaluate

    conn = db.connect()
    try:
        result = reevaluate(conn, args.job)
    except (ManualJobError, ValueError) as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False) if args.json else result)
    return 1 if "error" in result else 0


def cmd_apply_places(args: argparse.Namespace) -> int:
    """Set link, email and postal address to apply at once (JSON {url, email, address} in a file)."""
    import json
    from pathlib import Path

    from core.manual import ManualJobError, set_apply_places

    conn = db.connect()
    try:
        data = json.loads(Path(args.text_file).read_text(encoding="utf-8") or "{}")
        result = set_apply_places(conn, args.job, data.get("url"), data.get("email"), data.get("address"))
    except (ManualJobError, ValueError) as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False) if args.json else result)
    return 1 if "error" in result else 0


def cmd_apply_to(args: argparse.Namespace) -> int:
    """Set where to apply for a job: a link, or an email address (empty clears the link)."""
    import json

    from core.manual import ManualJobError, set_apply_target

    conn = db.connect()
    try:
        result = set_apply_target(conn, args.job, args.target)
    except (ManualJobError, ValueError) as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False) if args.json else result)
    return 1 if "error" in result else 0


def cmd_recruiters(args: argparse.Namespace) -> int:
    """The recruiter list (core §16c): list, add (tags all stored jobs at once), update, remove, and
    clear-job ("not a recruiter")."""
    import json

    from core import recruiters

    db.init_db()
    conn = db.connect()
    try:
        if args.action == "list":
            result = {"recruiters": recruiters.list_recruiters(conn)}
        elif args.action == "add":
            result = recruiters.add(conn, args.name or [], args.note)
        elif args.action == "update":
            result = recruiters.update(conn, args.id, args.name or [], args.note)
        elif args.action == "remove":
            result = {"id": args.id, "untagged": recruiters.remove(conn, args.id)}
        else:
            recruiters.clear(conn, args.job)
            result = {"job_id": args.job, "via_recruiter": "cleared"}
    except (ValueError, TypeError) as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif "error" in result:
        print(f"Error: {result['error']}")
    elif args.action == "list":
        for r in result["recruiters"]:
            print(f"{r['id']:>3}  {', '.join(r['names'])}  ({r['jobs']} jobs)")
    elif "tagged" in result:
        print(f"{result['names'][0]}: {len(result['tagged'])} job(s) tagged")
        for j in result["tagged"]:
            print(f"  {j['id']:>5}  {j['title']} — {j['company']}")
    else:
        print(result)
    return 1 if "error" in result else 0


def cmd_reminders(args: argparse.Namespace) -> int:
    """Job reminders that are due (core §16c); --notify sends them via Telegram. Runs every 15
    minutes from the scheduled task "JobHunter reminders" (setup-task.ps1)."""
    import json

    from core import reminders

    db.init_db()
    conn = db.connect()
    try:
        result = reminders.send_due(conn) if args.notify else {
            "due": [{"id": j["id"], "title": j["title"], "remind_at": j["remind_at"]} for j in reminders.due(conn)]}
    finally:
        conn.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif args.notify:
        print(f"reminders: {result['due']} due, {result['sent']} sent" + (f" ({result['result']})" if "result" in result else ""))
    else:
        for j in result["due"]:
            print(f"{j['id']:>5}  {j['remind_at']}  {j['title']}")
    return 0


def cmd_followups(args: argparse.Namespace) -> int:
    """Applications without a reply: due follow-ups and no-response reminders (--notify sends them)."""
    import json

    from core import followups

    db.init_db()
    conn = db.connect()
    try:
        if args.notify:
            result = followups.send_reminders(conn)
        else:
            found = followups.due(conn)
            result = {k: [{"id": j["id"], "title": j["title"], "company": j["company"], "days": j["days"]} for j in v]
                      for k, v in found.items()}
    finally:
        conn.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif args.notify:
        print(f"follow-up reminders: {result['follow_up']} follow-up, {result['no_response']} no reply → {result['sent']}")
    else:
        for kind, jobs_ in result.items():
            print(f"{kind}: {len(jobs_)}")
            for j in jobs_:
                print(f"  #{j['id']} {j['title']} – {j['company']} ({j['days']} days)")
    return 0


def cmd_followup_text(args: argparse.Namespace) -> int:
    """A ready follow-up message (subject + body) for an applied job, in the application's language."""
    import json

    from core import followups
    from core.profile import ProfileError, load_profile

    conn = db.connect()
    try:
        job = next((j for j in followups.applied_jobs(conn) if j["id"] == args.job), None)
        if job is None:
            result = {"error": f"job {args.job} is not in status applied"}
        else:
            try:
                name = (load_profile()[0].get("personal") or {}).get("name", "")
            except ProfileError as e:
                name = ""
                print(f"[followup-text] {e}", file=sys.stderr)
            result = followups.followup_text(job, name)
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False) if args.json else result.get("error") or
          f"Subject: {result['subject']}\n\n{result['body']}")
    return 1 if "error" in result else 0


def cmd_followed_up(args: argparse.Namespace) -> int:
    import json

    from core import followups

    conn = db.connect()
    try:
        followups.mark_followed_up(conn, args.job)
        result = {"ok": True}
    except ValueError as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    print(json.dumps(result) if args.json else result)
    return 1 if "error" in result else 0


def cmd_check_profile(args: argparse.Namespace) -> int:
    """Validate a profile file (the UI's profile editor checks before saving)."""
    import json
    from pathlib import Path

    from core.profile import ProfileError, load_profile

    try:
        _, warnings = load_profile(Path(args.path) if args.path else None)
        result = {"ok": True, "warnings": warnings}
    except ProfileError as e:
        result = {"error": str(e)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result.get("error") or "\n".join(["profile OK"] + [f"warning: {w}" for w in result["warnings"]]))
    return 1 if "error" in result else 0


def cmd_rename_documents(args: argparse.Namespace) -> int:
    """One-off: rename cv.pdf/anschreiben.pdf/cover_letter.pdf to <Name>_<Title>_<Document>.pdf."""
    from core.applications import rename_legacy_documents
    from core.profile import load_profile

    conn = db.connect()
    try:
        renamed = rename_legacy_documents(conn, (load_profile()[0].get("personal") or {}).get("name", ""))
    finally:
        conn.close()
    for job_id, old, new in renamed:
        print(f"job {job_id}: {old} → {new}")
    print(f"{len(renamed)} file(s) renamed.")
    return 0


def cmd_setting(args: argparse.Namespace) -> int:
    """Print one setting's value (used by run.ps1 for run_model)."""
    db.init_db()
    conn = db.connect()
    try:
        value = db.get_settings(conn).get(args.key)
    finally:
        conn.close()
    if value is None:
        print(f"Error: no setting {args.key}", file=sys.stderr)
        return 1
    print(value)
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    from core import setup
    try:
        return setup.run()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup stopped. Steps already answered are saved; run it again to continue.")
        return 1


def cmd_agent(args: argparse.Namespace) -> int:
    """One run stage with an OpenAI-compatible provider (LLM_PROVIDER ≠ claude-code)."""
    from core import agent
    return agent.main(args.trigger, args.stage, args.job)


def cmd_llm_provider(args: argparse.Namespace) -> int:
    """Print LLM_PROVIDER (claude-code by default); run.ps1/run.sh pick claude -p or the agent by it."""
    from core import agent
    print(agent.provider_name())
    return 0


def _print_filters(conn) -> None:
    filters = load_filters(conn)
    if not filters:
        print("No filters yet. Run: uv run python cli.py seed-filters")
        return
    import json

    from core import countries
    default = json.loads(db.get_settings(conn).get("search_countries") or "[]") or countries.DEFAULT
    print(f"\n{'id':>3}  {'active':6}  {'name':24}  {'where':24}  keywords")
    for f in filters:
        where = f.location or ", ".join(countries.label(c) for c in (f.countries or default))
        print(f"{f.id:>3}  {'yes' if f.active else 'no':6}  {f.name:24}  {where:24}  {', '.join(f.keywords)}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # umlauts on Windows consoles
    parser = argparse.ArgumentParser(prog="cli.py", description="JobHunter CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Guided first-time setup: AI provider, mail, Telegram, work permit, filters"
                   ).set_defaults(func=cmd_setup)
    sub.add_parser("init-db", help="Create data/jobhunter.db and apply migrations").set_defaults(func=cmd_init_db)
    sub.add_parser("seed-filters", help="Insert the default search filters").set_defaults(func=cmd_seed_filters)
    sub.add_parser("filters", help="List search filters").set_defaults(func=cmd_filters)
    p = sub.add_parser("search", help="Run a filter against the job sources")
    p.add_argument("--filter", type=int, required=True, help="Filter id (see: cli.py filters)")
    p.add_argument("--source", choices=["ba_jobsuche", "arbeitnow", "jobspy", "himalayas", "jobicy", "email_alerts"], help="Only this source")
    p.add_argument("--limit", type=int, default=20, help="Max postings per source (default 20)")
    p.add_argument("--dry-run", action="store_true", help="Search and screen, but store nothing")
    p.set_defaults(func=cmd_search)
    sub.add_parser("render-test", help="Render CV + letter (DE/EN) from templates/examples/ into output/_render-test/"
                   ).set_defaults(func=cmd_render_test)
    sub.add_parser("telegram-setup", help="Print the chat id after you messaged the bot").set_defaults(func=cmd_telegram_setup)
    sub.add_parser("telegram-test", help="Send a test message to TELEGRAM_CHAT_ID").set_defaults(func=cmd_telegram_test)
    p = sub.add_parser("notify-failure", help="Mark open runs failed and send a 'Run failed' Telegram message")
    p.add_argument("--reason", default="claude exited with an error")
    p.add_argument("--log", help="Log file to point to")
    p.set_defaults(func=cmd_notify_failure)
    p = sub.add_parser("apply-kit", help="Print the apply kit (prompt, fields, files) for a job")
    p.add_argument("job", type=int)
    p.add_argument("--json", action="store_true", help="Everything as JSON")
    p.set_defaults(func=cmd_apply_kit)
    p = sub.add_parser("add-job", help="Add a job by link and/or pasted posting text")
    p.add_argument("--url", required=True)
    p.add_argument("--text-file", help="UTF-8 file with the full posting text")
    p.add_argument("--title")
    p.add_argument("--company")
    p.add_argument("--location")
    p.add_argument("--apply-to", help="Where to apply: a link (ATS form) or an email address")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_add_job)
    p = sub.add_parser("reevaluate", help="Evaluate a job again with its current posting text")
    p.add_argument("job", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reevaluate)
    p = sub.add_parser("apply-to", help="Set where to apply for a job (link or email; empty clears)")
    p.add_argument("job", type=int)
    p.add_argument("target", nargs="?", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_apply_to)
    p = sub.add_parser("apply-places", help="Set link, email and postal address to apply (JSON file)")
    p.add_argument("job", type=int)
    p.add_argument("--text-file", required=True, help="JSON {url, email, address}; empty values clear")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_apply_places)
    p = sub.add_parser("update-posting", help="Add/replace a job's full posting; it gets evaluated again")
    p.add_argument("job", type=int)
    p.add_argument("--text-file", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_update_posting)
    p = sub.add_parser("recruiters", help="Recruiting agencies: list/add/update/remove; clear-job = 'not a recruiter'")
    p.add_argument("action", choices=["list", "add", "update", "remove", "clear-job"])
    p.add_argument("--name", action="append", help="Name or another spelling (repeat for several)")
    p.add_argument("--note")
    p.add_argument("--id", type=int, help="Recruiter id (update/remove)")
    p.add_argument("--job", type=int, help="Job id (clear-job)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_recruiters)

    p = sub.add_parser("reminders", help="Job reminders that are due; --notify sends them via Telegram")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reminders)

    p = sub.add_parser("followups", help="List applications due for a follow-up / with no reply; --notify sends the reminders")
    p.add_argument("--notify", action="store_true", help="Send due reminders by Telegram (each only once)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_followups)
    p = sub.add_parser("followup-text", help="Print a ready follow-up message for an applied job")
    p.add_argument("job", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_followup_text)
    p = sub.add_parser("followed-up", help="Record that you sent a follow-up for a job")
    p.add_argument("job", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_followed_up)
    p = sub.add_parser("check-profile", help="Validate a profile YAML file (default: profile/profile.yaml)")
    p.add_argument("--path", help="File to check instead of profile/profile.yaml")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check_profile)
    sub.add_parser("rename-documents", help="Rename old cv.pdf/anschreiben.pdf files to <Name>_<Title>_<Doc>.pdf"
                   ).set_defaults(func=cmd_rename_documents)
    p = sub.add_parser("setting", help="Print one setting's value")
    p.add_argument("key")
    p.set_defaults(func=cmd_setting)
    p = sub.add_parser("agent", help="Run one stage with another LLM provider (used by run.ps1/run.sh)")
    p.add_argument("--trigger", default="manual",
                   choices=["scheduled", "manual", "docs", "single", "evaluate"])
    p.add_argument("--stage", required=True,
                   choices=["filter", "write", "docs", "evaluate", "single", "single-write"])
    p.add_argument("--job", type=int, default=0)
    p.set_defaults(func=cmd_agent)
    sub.add_parser("llm-provider", help="Print LLM_PROVIDER from .env (claude-code by default)"
                   ).set_defaults(func=cmd_llm_provider)
    p = sub.add_parser("check-run", help="Exit 1 if a run started since --since is still open")
    p.add_argument("--since", required=True, help="UTC timestamp 'YYYY-MM-DD HH:MM:SS'")
    p.set_defaults(func=cmd_check_run)
    p = sub.add_parser("mail-test", help="Check IMAP login + Drafts folder; never sends")
    p.add_argument("--account", choices=["send", "alerts"], default="send",
                   help="send (drafts, default) or alerts (read-only job-alert inbox)")
    p.add_argument("--create", action="store_true", help="Save a 'JobHunter test' draft to yourself (send only)")
    p.add_argument("--job", type=int, help="With --create: attach this job's CV + letter from output/<job>/")
    p.set_defaults(func=cmd_mail_test)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
