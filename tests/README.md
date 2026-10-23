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

## Added 2026-10-22 (passed 2026-10-22: 198 tests)

| Test | Checks |
|---|---|
| `test_default_is_cv_only_unless_the_user_picks` (`tests/test_phase7a.py`) | Runs write only the CV by default; a letter is refused; the user's per-job "CV + cover letter" wins; a bad setting falls back to CV only |
| `test_file_names_use_first_and_last_name_only` (`tests/test_phase7a.py`) | "Max Peter Mustermann" → `Max_Mustermann_…`; Motivationsschreiben names are recognised |
| `test_motivation_only_on_request_and_keeps_cv_and_letter` (`tests/test_phase7a.py`) | Motivationsschreiben refused unless requested; written alone; CV and letter stay; a later CV/letter render keeps it; its path is stored |
| `test_text_naming_link_and_email_keeps_both` (`tests/test_apply_favorites_notify.py`) | A posting naming a link and an email keeps both |
| `test_set_apply_places` (`tests/test_apply_favorites_notify.py`) | Link, email and postal address saved together; empty clears one; bad input refused |
| `test_single_document_render_keeps_the_other` (`tests/test_phase7a.py`) | "Cover letter only" after a CV keeps the CV unchanged; both paths saved; a render in the other language replaces both |

**Changed:** the `shortlisted` fixture in `tests/test_mcp_tools.py` sets `default_documents = both`,
because those tests check the letter.

Check by hand:

18. **Settings → Documents to write…** shows `cv`; a job page's selector preselects "CV only"; the
    next run writes only the Lebenslauf. Switch to `both` and the letter comes back.
19. **Motivationsschreiben:** job page → Documents → "Motivationsschreiben (extra, on request)" →
    Generate now. The PDF appears next to the CV/letter, which stay unchanged.
20. **Where to apply:** fill link, email and postal address on a job page → three boxes with copy
    buttons; empty one field and save → only that one disappears.
21. **My notes:** type notes on a job page → Save notes → "Last saved …"; reload → still there;
    edit and save again → updated; empty and save → cleared.

## Added 2026-10-21 (passed 2026-10-21)

```powershell
uv run pytest -q tests/test_followups.py
```

| Test | Checks |
|---|---|
| `test_feedback_status_stops_reminders` (`tests/test_followups.py`) | A job in status `feedback` (employer replied, no interview) gets no follow-up reminder |

Check by hand:

15. **Feedback received** (job page of an applied job): pick it in the status dropdown (with a note) →
    the Follow-up panel is gone, the job stays in Applications and shows "Rückmeldung erhalten" in the
    CSV / Nachweis, and Statistics counts it.
16. **Phone** (or DevTools at 390 px): Jobs page shows cards, a full-width search box and the sort bar;
    the menu scrolls sideways; Runs / Needs you / Applications / Job boards show cards; no page
    scrolls sideways.
17. **Tunnel:** `UI_TUNNEL_HOSTS=.trycloudflare.com` in `.env`, `cd ui; npm run build; npm start`, then
    `cloudflared tunnel --url http://127.0.0.1:5173`. The tunnel URL redirects to `/login`; a code from
    Settings → Pair a device lets the phone in; saving a form works over the tunnel.

## Added 2026-10-19 (passed 2026-10-21)

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

## Added 2026-10-25: shareable setup

`uv run pytest -q tests/test_setup.py tests/test_agent.py tests/test_mail_config.py tests/test_search.py`

| File · test | Checks |
|---|---|
| `test_setup.py` · `test_write_env_keeps_comments_and_order` | The wizard edits `.env` in place: comments and order kept, new keys appended |
| `test_setup.py` · `test_parse_filter_lines` | "Name: title, title" lines → filters |
| `test_setup.py` · `test_groq_gmail_only_eu_citizen_own_filters` | Scripted wizard: Groq with models picked from the list, Gmail drafts (host guessed), alerts from the same mailbox, no Telegram, no work permit, own filters; secrets never printed |
| `test_setup.py` · `test_claude_code_yahoo_drafts_gmail_alerts` | Scripted wizard: Claude Code, Yahoo drafts plus Gmail alerts (mixed providers), starter filters |
| `test_agent.py` (6 tests) | Provider presets and key handling (key never in `repr`), model per stage, `read_file` only opens templates/skills (never `.env`/profile), old tool results trimmed first, 429 retry, fast failure on 400 |
| `test_mail_config.py` (new tests) | Host from the address (gmail, web.de, gmx, ymail), `*_MAIL_PROVIDER` presets, explicit host wins, unknown provider refused, mail optional |
| `test_search.py` · `test_work_permit_checks_off_flags_nothing` | With `work_permit_checks = 0` nothing is flagged, but the salary is still read |

**By hand, still to do:**
- a real run with an OpenAI-compatible provider (e.g. Groq): `LLM_PROVIDER=groq` in `.env`, models via `cli.py setup`, then `.\run.ps1 -Trigger manual`;
- `run.sh` on Linux/macOS.

## Added 2026-10-25: target countries, remote boards, required Telegram, delete

`uv run pytest -q tests/test_countries.py tests/test_setup.py`

| File · test | Checks |
|---|---|
| `test_countries.py` · `test_parse_and_aliases`, `test_effective_countries_filter_overrides_setting` | Names and aliases → keys; a filter's countries replace the setting; no setting → Germany |
| `test_countries.py` · `test_geo_matches` | Jobicy locations: Anywhere, country lists, regions (EMEA, Europe, LATAM) |
| `test_countries.py` · `test_covers` | BA/Arbeitnow only for Germany; Himalayas/Jobicy only when remote is wanted |
| `test_countries.py` · `test_feed_cache_reuses_within_six_hours` | A second fetch within 6 h comes from the cache; after 6 h it is fetched again |
| `test_countries.py` · `test_himalayas_targets_and_seven_days` | `worldwide=true` and `country=US`, jobs older than 7 days and non-matching titles dropped, the second run from the cache |
| `test_countries.py` · `test_jobicy_one_download_matched_per_filter` | One download serves several filters; country and age matched locally |
| `test_countries.py` · `test_jobspy_searches_each_country` | Indeed per country, no Glassdoor where it has no site, LinkedIn "Worldwide" for remote, limit shared |
| `test_setup.py` (updated + 3 new) | Countries step (menu numbers, unknown names refused), Telegram required: empty and wrong tokens refused, waits for the message, test message sent; a working bot can be kept |

**By hand:**
- a run with `search_countries` = `["usa", "remote"]` against the real boards;
- 🗑 Delete in the UI: the confirm step on the list and the job page, then `output/<id>/` is gone.
