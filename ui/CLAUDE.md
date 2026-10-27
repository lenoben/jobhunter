# JobHunter web UI

Part of the JobHunter blueprint (root `CLAUDE.md`, whose hard rules R1–R11 apply here too).

---

## 12. Web UI (`ui/`, SvelteKit at http://localhost:5173)

| Page | Content |
|------|---------|
| `/` Jobs | Table: title, company, location, work mode, fit score, status, first seen. Filter by status/source/work mode, search box. "Needs you" count badge in the header. **Pagination**: 50 per page (`?page=N`, page size selectable 25/50/100), with prev/next and "x–y of z". **Sorting**: click a column header (title, company, location, mode, fit, status, first seen) to sort; click again to reverse (`?sort=fit&dir=desc`; a fit score of "none" sorts last). Filters, sort and page stay in the URL. Row buttons: **Apply anyway** (skipped) / **Write docs** (no documents yet) and ✕ Not interested. A banner with **Generate now** appears while requested documents are waiting. |
| `/jobs/[id]` | Full posting, fit notes, **Project suggestions** (R11: own section from `jobs.project_suggestions`: title, scope, days, requirement covered), status dropdown + note (writes `status_history` with `changed_by='user'`), "Mark as applied" (sets `applied_at`), links to PDFs, `notes.md` rendered, interview prep, history timeline, **Apply kit** panel (§13). Buttons: **Apply anyway** on skipped jobs (→ `shortlisted` + `docs_requested`) and **Write documents** on shortlisted jobs below the threshold (→ `docs_requested`). The next run's writer stage then tailors them even if the fit is below the threshold. Also available as a row button in the Jobs list. |
| `/attention` | Only `needs_attention` jobs with reasons and what to do. For `inferred_facts`: the list (statement, where, basis) with **Approve** (→ `docs_ready`, sets `applications.inferred_approved_at`, `changed_by='user'`) and **Reject** (back to `shortlisted` for a re-render without them). |
| `/filters` | List, create, edit, toggle active, delete search filters (all fields in §4), incl. `countries` (comma-separated, empty = setting `search_countries`; `ui/src/lib/countries.ts` mirrors `core/countries.py`). |
| `/runs` | Run history with counts and per-source errors. |
| `/settings` | `search_countries` (kind `countries`), `max_tailored_per_run`, `min_hours_between_runs`, Telegram on/off, the models (Claude Code and, for another provider, `llm_model_filter`/`llm_model_writer`), `work_permit_checks` (core §16), "Run now" button (spawns `run.ps1` with trigger `manual`). |

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

**Phones (2026-10-21):** below 700px the menu is one sideways-scrolling row (the current page's
link is scrolled into view), text fields take their own line, and inputs use 16px (no iOS zoom).
`table.stack` (app.css) turns a table into one card per row; `td[data-label]` shows its column
name, `td.full` takes a whole line, `td.first` moves to the top. Used by Jobs (with a sort bar
instead of the hidden headers), Runs, Needs you (alert review), Applications and Job boards.
Checked with DevTools phone emulation at 390px: no page is wider than the screen.

**Reverse tunnel** (user request 2026-10-21, e.g. Cloudflare). This relaxes R4 further: the UI is
reachable from the internet and its traffic passes through the tunnel provider.
- `.env`: `UI_TUNNEL_HOSTS` = the tunnel's host names (`.trycloudflare.com` = any quick tunnel, or
  your own hostname), plus `UI_SESSION_SECRET`.
- cloudflared connects from loopback, so `hooks.server.ts` recognises a tunnel request by its Host
  header (`access.isTunnelHost`) and treats it like a hotspot device: a paired `jh_device` cookie
  (Secure over the tunnel) or `/login`. Without that check every tunnel visitor would count as
  "this PC". Pairing codes are still created only on the PC itself.
- The same-origin check accepts `https://<tunnel host>` (TLS ends at Cloudflare). `serve.js`
  reports https to SvelteKit when cloudflared, from loopback only, sends `X-Forwarded-Proto: https`.
- **Production server only** (`npm run build`, `npm start`). Vite's dev server serves its own file
  routes (`/@fs/`, `/src/…`) outside the guard, so `vite.config.ts` doesn't allow tunnel hosts.
- Start: `cloudflared tunnel --url http://127.0.0.1:5173` (127.0.0.1, not localhost: the server
  listens on IPv4 only). A quick tunnel gets a new URL each start, so devices pair again; a named
  tunnel with a fixed hostname keeps them paired.

**My notes** (user request 2026-10-22): the job page has a "My notes" card below the status, a
free-text field for the user's own notes on the application process (calls, contacts, next steps).
Saved in `jobs.user_notes` with `user_notes_at` (migration 017) by `db.saveUserNotes`, max 20,000
characters; an empty field clears them. Never read by Claude or used in the documents.

**Delete a job** (user request 2026-10-25, core §16b): `ConfirmDelete.svelte` is a two-step button
(no browser dialog, so it works on phones). Used on `/` (row, 🗑) and `/jobs/[id]` (redirects to
`/?deleted=1`). The actions refuse without `confirm=yes`.

Settings `kind: 'text'` may be `optional` (empty allowed): `llm_model_filter` / `llm_model_writer`
are empty for Claude Code users and blocked every save before 2026-10-25.

**Recruiters, reminders, author credit** (user requests 2026-10-28, core §16c):
- `/recruiters`: add an agency (name + other spellings, comma-separated, + note) → **Add & tag
  jobs** calls `cli.py recruiters add` and lists the stored jobs it tagged right away; edit/remove
  (two-step `ConfirmDelete` with `label="Remove"`); a "Found by the scoring model" table with
  **+ List** / ✕ (not a recruiter). The menu shows 🤝 N = tagged jobs not opened yet.
- Jobs list: 🤝 Recruiter and ⏰ date tags next to the title; filters **🤝 Via recruiter**
  (`?recruiter=1`, or `?recruiter_id=N` from /recruiters) and **⏰ Reminders** (`?reminders=1`).
- Job page: a 🤝 card (why it's tagged; "Add <company> to my recruiter list"; "✕ Not a recruiter"),
  and for untagged jobs a small "Add to my recruiter list" in Facts. The Documents card explains
  that recruiter jobs get documents only on request. A **⏰ Reminder** card (date, time, note;
  Change / Remove; saved in `db.setReminder`, local time). Opening the page sets `recruiter_seen`.
- `+layout.svelte`: a "by lenoben" byline pill next to the brand and a footer on every page
  ("Built by lenoben · lenoben.top · Source on GitHub"). These are the project author's credit
  (constants `AUTHOR`, `AUTHOR_URL`, `REPO_URL`), the same for everyone who uses the project — not
  taken from the user's profile. Styles in `app.css` (`.byline`, `.site-footer`, `.tag`).
- Checked 2026-10-28: `svelte-check` 0 errors; pages load; screenshots of /recruiters and a job page.
- `/stats` (2026-10-28): **Rejected** and **Withdrawn** also as stat tiles (last 30 days / 12 months)
  and in "Right now" (links to `/?status=rejected|withdrawn`); the charts already had them.
