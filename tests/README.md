# New tests to run later (added 2026-10-18)

These tests cover today's additions. They run offline: fake IMAP, HTTP and Telegram, each on its
own temporary database, so your real `data/jobhunter.db` is never touched.

Status when written: all 185 tests passed (`uv run pytest -q`, 2026-10-18).

## Run only the new tests

```powershell
cd D:\projekte\jobhunt
uv run pytest -q tests/test_apply_favorites_notify.py
uv run pytest -q tests/test_email_alerts.py -k "apply_with_profile or keyword_match_variants or no_cap_and_unmatched"
```

Everything at once: `uv run pytest -q`.

## The new tests

**`tests/test_apply_favorites_notify.py`** (new file)

| Test | Checks |
|---|---|
| `test_apply_target_from_text` (5 cases) | An application link or email is found next to "bewerben / apply / Bewerbung / Unterlagen"; other links and privacy addresses are ignored |
| `test_apply_link_from_page_buttons` | A page's "Jetzt bewerben" button gives the apply link; mailto links don't |
| `test_add_job_takes_the_apply_link_from_the_text_or_the_user` | "+ Add a job" stores the link from the text, or the link/email the user typed; invalid input is refused |
| `test_evaluation_keeps_the_apply_email` | An evaluation doesn't drop an apply email set earlier |
| `test_unscored_job_in_another_status_is_scored_without_status_change` | Jobs without a score get one, keep their status, and don't count as "docs ready" |
| `test_reevaluate` | Re-evaluate: skipped → new; docs_ready keeps its status and loses only the score |
| `test_evaluate_trigger_skips_the_time_guard` | "Score waiting jobs" isn't blocked by `min_hours_between_runs` |
| `test_purge_old_jobs_keeps_what_matters_and_dedups` | Automatic clean-up: off at 0; deletes only untouched jobs; keeps applied jobs, ★ favourites and requested documents; deleted jobs stay "seen" (R8) but can be added again by hand |
| `test_docs_run_lists_written_and_waiting_jobs` | Telegram after "Generate now": the documents written and the jobs still waiting |
| `test_single_run_reports_the_score` | Telegram after "Evaluate now": fit score and decision |
| `test_notification_toggles` | The `notify_*` settings switch messages off; a run that can't start sends "⏸ … couldn't start" |

**`tests/test_email_alerts.py`** (new tests in an existing file)

| Test | Checks |
|---|---|
| `test_parse_apply_with_profile_lines` | LinkedIn mails with "Apply with resume & profile" / "Apply now" / "N company alumni" no longer shift title → company → city |
| `test_keyword_match_variants` (8 cases) | "Full-Stack" / "Full Stack" / "Fullstack" and "Software-Entwickler" / "Softwareentwickler" match; "Go Developer" doesn't match "Django Developer" |
| `test_no_cap_and_unmatched_jobs_kept_for_review` | Alert jobs aren't capped at 10 per filter; jobs matching no filter are kept as "alert review" |

**Changed:** in `tests/test_mcp_tools.py`, `test_evaluate_and_flag` now expects the new message
"already scored", because scoring unscored jobs is allowed.

## Added 2026-10-19 (not run yet)

```powershell
uv run pytest -q tests/test_followups.py
```

**`tests/test_followups.py`** (new file)

| Test | Checks |
|---|---|
| `test_due_reminders_and_each_is_sent_once` | Follow-up due after 14 days, "no reply" after 42; the date also comes from the history when the status was set from the dropdown; one Telegram message; never sent twice |
| `test_followed_up_stops_the_reminder_and_keeps_the_status` | "I followed up" stops the reminder, keeps status applied, writes a history line |
| `test_settings_switch_reminders_off` | `notify_followups = 0` sends nothing and marks nothing; `followup_after_days = 0` turns the reminder off |
| `test_failed_telegram_marks_nothing` | If Telegram fails, the reminder is sent next time |
| `test_followup_text_in_the_application_language` | German / English text, gender tag removed from the title, ends with your name |
| `test_check_profile_reports_errors` | A profile without required sections is refused (used by the profile editor) |

Check by hand:

11. **Applications** page: list, date filter, **CSV (Excel)** opens in Excel with umlauts, **Record for the
    Agentur (PDF)** prints on A4 landscape without the menu bar.
12. **Job page of an applied job → Follow-up:** "Show follow-up text", copy buttons, "I followed up".
13. **Profile → Motivation:** change one category, save; only that entry changes in `profile.yaml`, the old
    file is in `profile/backups/`. A broken YAML in "Whole profile" is refused.
14. **Telegram:** the next scheduled run sends "📬 No reply after 14+ days" once the first applications
    are 14 days old (from about 30.10.2026).

## Check by hand (UI, Telegram, real runs)

1. **Generate now:** documents are written; Telegram says "✍️ Requested documents: N written".
2. **Evaluate now / Re-evaluate** (job page): the fit score appears after 1–3 minutes; Telegram
   reports it.
3. **Score waiting jobs** (Jobs page): up to 60 jobs are scored, then documents are written for the
   ones that qualify.
4. **Where to apply:** a posting that names an application link or address → the job page shows
   "Apply here ↗" or the email address.
5. **Favourites:** ☆/★ in the list and on the job page; the "★ Favourites" filter.
6. **Needs you → Job-alert jobs to review:** tick jobs → Evaluate in next run / Evaluate now /
   Not interested.
7. **Job boards:** save, edit, open in a new tab, delete.
8. **Statistics:** Daily/Monthly, hover tooltips, the per-status grid, the tables.
9. **Settings → Delete untouched jobs after … days:** the note shows how many jobs would go.
10. **Settings → Pair a device:** visible only on the PC itself.

Before using the built UI (`npm start`), build it once: `cd ui; npm run build`. The dev server
(`npm run dev`) doesn't need this.
