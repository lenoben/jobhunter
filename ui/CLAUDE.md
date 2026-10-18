# JobHunter web UI

Part of the JobHunter blueprint (root `CLAUDE.md`, whose hard rules R1–R11 apply here too).

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
