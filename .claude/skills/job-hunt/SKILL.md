---
name: job-hunt
description: The JobHunter run — search the active filters, evaluate new jobs (filter stage), tailor the CV and, if wanted, the cover letter (write stage), and report via Telegram. Use when asked to run the job-hunt workflow (scheduled, manual or docs; stage filter, write or docs).
---

# Job-hunt run

You run unattended (`claude -p`). Only the `jobhunter` MCP tools and `Read` inside this project
are available. Nobody answers questions, so never ask any. The prompt names the **Trigger** and
the **Stage**. Do only that stage's steps.

| Stage | Who | Steps |
|---|---|---|
| `filter` | cheap model | A1–A4: start the run, search, evaluate. Do **not** write documents and do **not** call `finish_run`. |
| `write` | writer model | B1–B3: write documents for the open run, then `finish_run`. |
| `docs` | writer model | C1: "Generate now" from the UI, for the jobs the user requested documents for. |
| `evaluate` | cheap model | E1: "Score waiting jobs" from the UI: evaluate the backlog of `new` jobs, no search. Do **not** call `finish_run`; the write stage follows. |
| `single` | cheap model | D1: "Evaluate now" for **one** job (`Job: N` in the prompt). Do **not** call `finish_run` unless you stop early. |
| `single-write` | writer model | D2: documents for that one job, if it qualifies, then `finish_run`. |

## Hard rules (CLAUDE.md §1, short form)
- **R1:** never submit anything and never send email. `save_email_draft` only saves a draft.
- **R5:** use only facts from `get_profile`. Anything else is a gap: put it in `fit_notes`, never in
  the documents.
- **R8:** never work on a job twice. Only `evaluate_job` jobs with status `new`. Jobs that are
  already `needs_attention` (e.g. the salary or work-authorization screening hit) are left alone.
- **R9:** you may add an *inferred fact* only when the profile clearly implies the ability. It must
  be a capability or learning statement ("kann mich schnell in X einarbeiten", "Grundlagen in X
  durch Y"), never claimed experience, years, employers, grades or certificates. List it in that
  document's `inferred` array as `{text, where, basis}`. The job then waits for the user's approval.
  **Never reuse anything in `get_profile().rejected_inferences`.** `render_documents` rejects both
  violations.
- **R10:** a cover letter mentions at most **2–3** projects or experiences, chosen for relevance
  and each tied to a specific requirement of the posting. Leave unrelated ones out, even
  impressive ones. The CV may list more, with projects and skills ordered by relevance.
- **R11:** project ideas for gaps go only into `project_suggestions` (and so the UI), never into
  documents.
- Personal data stays in the tools and the documents. Don't repeat it in your final answer.

## Stage `filter`
**A1.** Call `start_run` with the trigger from the prompt (`scheduled` or `manual`). If it returns
`started: false`, reply with one line quoting the reason and **stop**.

**A2.** Call `get_settings`, `get_profile` and `get_active_filters`. Remember
`max_evaluated_per_run`, and each filter's `min_fit_score`, `exclude_freelance`,
`exclude_keywords`, `employment_types` and `work_modes`.

**A3. Search:** call `search_jobs(filter_id)` once per active filter, without `sources` or `limit`.
Source errors are recorded automatically; carry on.

**A4. Evaluate:** call `list_jobs("new", limit = max_evaluated_per_run)`. For each job: `get_job`,
then `evaluate_job`:
- Classify `work_mode`, `employment_type`, `language` (the posting's), and `apply_method`, with
  `apply_email` when the posting names an application address. If the job already has an
  `apply_email` (set by the user or taken from the posting), it is kept, so use `email`. If it has
  an `apply_url` (where to apply), use `external_ats` or `portal` for that link.
- Use **skip** for freelance/self-employed (if `exclude_freelance`), an excluded keyword, an
  unwanted employment type or work mode, or a poor fit.
- `fit_score` (0–100) against the profile: skills, experience level, language, location. Take the
  user's city from `personal.address`, the language levels from `languages[]`, and their
  willingness to relocate from `preferences.notes`.
- `fit_notes`: short Markdown bullets with the match, the gaps, and R9 candidates. Add "Salary not
  stated" if `salary_flag` is `salary_unknown`.
- `project_suggestions` (R11), for every job with real gaps: 1–3 items
  `{title, scope, days, covers}`. Make them small and realistic: build on the user's stack and
  existing projects where possible.
- Use **shortlist** only when `fit_score ≥` the filter's `min_fit_score`.

Then reply with one line ("evaluated N, shortlisted M") and **stop**. Do not call `finish_run`; the
write stage does that.

## Stage `write`
**B1.** Call `current_run`. If `run_id` is null, reply "no open run" and stop. Otherwise call
`get_settings` and `get_profile`.

**B2.** Call `list_jobs("shortlisted", for_documents = true, limit = max_tailored_per_run)`. This
returns jobs with fit ≥ `min_fit_for_documents`, and jobs the user requested (`docs_requested`),
requested ones first. For each job, run **Tailor one job** (below).

**B3.** Call `finish_run(run_id)` and reply with its `summary` line.

## Stage `docs`
**C1.** Call `start_run("docs")`. If it is refused, reply with the reason and stop. Call
`get_settings` and `get_profile`, then
`list_jobs("shortlisted", for_documents = true, requested_only = true, limit = 10)`. For each job,
run **Tailor one job**. Then call `finish_run(run_id)` and reply with the summary line.

## Stage `evaluate` (backlog, no search)
**E1.** Call `start_run("evaluate")`. If it is refused, reply with the reason and stop. Call
`get_settings`, `get_profile` and `get_active_filters`, then `list_jobs("new", limit = 60)` and
evaluate every job exactly as in A4. Reply with one line ("evaluated N, shortlisted M") and **stop**.
Do not call `finish_run`; the write stage does that.

## Stage `single` (one job the user added, or whose full posting they added)
**D1.** Call `start_run("single")`. If it is refused, reply with the reason and stop. Call
`get_settings`, `get_profile` and `get_job(N)`.
- If the job's status is `new`, evaluate it exactly as in A4, including `project_suggestions`.
  Jobs added by hand may have no filter. Then use the default `min_fit_score` of 60.
- If it has **no `fit_score`** but another status (documents were requested before it was
  evaluated, or the user asked to re-evaluate it), call `evaluate_job` the same way. It stores the
  score, notes and project ideas and keeps the status (pass the decision you would make anyway).
- If its status is `new` but `needs_attention`-flagged by the §5a screening, or it is already
  scored and not `new`, don't evaluate it. Call `finish_run(run_id)`, reply with one line
  explaining why, and stop.
- Otherwise reply with "evaluated job N: <decision>, fit <score>" and **stop**, leaving the run open.

## Stage `single-write`
**D2.** Call `current_run`, `get_settings`, `get_profile` and `get_job(N)`.
- If the job is `shortlisted` and (`fit_score ≥ min_fit_for_documents` or `docs_requested`), run
  **Tailor one job** for it.
- Otherwise write nothing.

Then call `finish_run(run_id)` and reply with one line: documents written, or why not (e.g. "fit
54 < 60").

## Tailor one job
1. Call `get_job`. Note `filter_name`, `language` and `docs_requested`. If `fit_score` is null
   (the user requested documents before the job was evaluated), first call `evaluate_job` as in A4
   (with `project_suggestions`): it only stores the score and notes, the status stays. `Read`
   `templates/examples/cv_<lang>.json` (and `letter_<lang>.json` if you write a letter) once for
   the exact format.
2. **Which documents:** the job's `documents` field: `cv` → CV only (the default, setting
   `default_documents`), `letter` → cover letter only, `both` → both, `motivation` → only a
   **Motivationsschreiben** (rules below; the CV and letter stay as they are). Never write a
   document it doesn't ask for; `render_documents` refuses it.
3. Write the content (rules below) and call `render_documents`. If it returns an error, fix exactly
   what it names and call it again, at most 3 tries.
4. Call `save_application(job_id, summary, interview_prep, method)` (for a `motivation` request,
   pass the existing application's `interview_prep` and `method` unchanged and add one line about
   the Motivationsschreiben to its `summary`):
   - `summary`: what you emphasised and why. If `profile.motivation[filter_name]` was missing or
     too thin, add the line `⚠️ Motivation for "<filter_name>" missing/thin in profile.yaml`.
   - `interview_prep`: Markdown with likely questions, technical topics to revise, and 3 questions
     to ask them.
   - `method`: e.g. "Portal: <url>" or "Email to <address>".
5. If `apply_method` is `email` and the job has `apply_email`, call `save_email_draft`. The subject
   is the letter subject, or without a letter "Bewerbung als <title>" / "Application for <title>". The body is 3–5 sentences in the posting language, saying which documents
   are attached. A refusal (e.g. inferred facts not approved yet) is fine: carry on.
6. If something blocks (a hard requirement the profile lacks, or an unclear posting), call
   `flag_attention` with one sentence on what the user should do.

## Documents (CLAUDE.md §7)
**General**
- Language = the posting's language. German → Lebenslauf + Anschreiben (DIN 5008, formal *Sie*,
  "Mit freundlichen Grüßen"). English → CV + cover letter ("Dear …,", "Kind regards").
- Facts come only from the profile (R5). Name degrees, titles and employers exactly as the profile
  does: "B.Sc. Computer Engineering", never "Informatik". Never use "Ingenieur" in German.
- No visa, residence permit, Blue Card or work-authorization wording unless the posting asks for
  it.

**CV**
- At most 2 pages, dates as `MM/YYYY` with `present` for ongoing.
- **Headline** (user request 2026-10-18): `<role> | B.Sc. Computer Engineering`. `<role>` follows
  the posting's role family, so not "Full-Stack-Entwickler" by default. Use the posting's role
  (e.g. "Backend-Entwickler", "Embedded-Softwareentwickler", "Softwareentwickler mit Schwerpunkt
  DevOps", "Frontend-Entwickler", "Python-Entwickler") when the profile backs it with experience,
  projects or skills. Otherwise use the closest truthful role, usually "Softwareentwickler" (R5).
  Never put a seniority, an employer's job title the user didn't hold, or "Ingenieur" in it. English
  CVs follow the same rule ("Backend Developer | B.Sc. Computer Engineering").
- The German CV includes every experience entry with `include_in_cv.de: true`.
- Experience and education are sorted newest-first by the tool. Order `projects` and `skills` by
  relevance to the posting.
- Contact details come from `profile.personal`. Add the German `personal` rows (Geburtsdatum,
  Staatsangehörigkeit) only if the profile sets them. There is no photo field.
- **Grades in German:** "CGPA 3,45/4,00 (entspricht ca. <grade_de>, modifizierte bayerische
  Formel)", using `education[].grade_de`. Never compute it yourself.

**Motivationsschreiben** (only for `documents = motivation`; `Read`
`templates/examples/motivation_<lang>.json` for the format)
- An extra document, not the Anschreiben: 1–2 pages ✔, 4–9 paragraphs ✔, no cliché opener ✔,
  profile projects with their link ✔. `subtitle` = "<role> bei <company>" / "<role> at <company>".
- It answers *why*: why this field, why this company (from the posting), what drives the user
  (`profile.motivation[filter_name]`, never invented, R5), what they want to learn and where they
  want to go. Skills only as evidence for the motivation, never a second CV.
- Same facts, R9 and visa rules as the letter; list inferred statements under `inferred`.

**Cover letter: style rules** (the tool checks those marked ✔)
1. ✔ **No clichéd opener.** Not "mit großem Interesse habe ich Ihre Anzeige gelesen", not
   "hiermit bewerbe ich mich", not "I am writing to apply", not "I am applying for". Paragraph 1
   opens with the motivation for *this* role and company.
2. **Motivation** comes from `profile.motivation[filter_name]`, linked to what this company or role
   does. If it is missing or thin, use the strongest truthful link from profile facts and flag it
   in the summary (step 4). Never invent motives.
3. **German letters use German course names** from `focus_de` / `electives_de`, never the English
   originals.
4. **Strong, concrete verbs** (entwickelt, aufgebaut, eingeführt, automatisiert, betreut,
   verantwortet) instead of "unterstützt" or "mitgewirkt", but only where the profile backs the
   stronger claim.
5. **Correct German compounds:** IT-Leiter, Full-Stack-Entwickler, Backend-Entwicklung,
   CI/CD-Pipeline, Open-Banking-Plattform.
6. ✔ **4–5 short paragraphs:**
   1. motivation;
   2–3 (or 2–4). 2–3 requirements, each with one experience or project from the profile (R10);
   last. the closing paragraph.
7. ✔ **The closing paragraph states the availability:** start date (`availability.start_date`, e.g.
   "ab dem 01.02.2027") and hours. Add the location/language note only if relevant (on-site/hybrid,
   German-speaking team). The template signs with the full name.
8. ✔ **Every project you mention carries its link** from `projects[].url`, e.g. "Buchungskalender
   (github.com/<user>/kalender)".
9. Name the company. No sentence that would fit any job.
