// Server-only DB access for the UI (CLAUDE.md §12). Same SQLite file as the Python core; the
// schema is owned by core/migrations (Python) — this module never changes it.
import Database from 'better-sqlite3';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

export const STATUSES = [
	'new', 'skipped', 'shortlisted', 'docs_ready', 'needs_attention',
	'applied', 'feedback', 'interview', 'offer', 'rejected', 'withdrawn'
] as const;
// needs_attention needs a reason, so only Claude sets it.
export const USER_SETTABLE = STATUSES.filter((s) => s !== 'needs_attention');
export const WORK_MODES = ['remote', 'hybrid', 'onsite'];
export const EMPLOYMENT_TYPES = ['full_time', 'part_time', 'minijob', 'working_student', 'internship'];
export const LANGUAGES = ['de', 'en'];
export const SOURCES = ['ba_jobsuche', 'arbeitnow', 'jobspy', 'email_alerts'];

/** Project root = the folder with pyproject.toml, found upward from the working directory. */
function findRoot(): string {
	if (process.env.JOBHUNTER_ROOT) return resolve(process.env.JOBHUNTER_ROOT);
	let dir = process.cwd();
	for (;;) {
		if (existsSync(join(dir, 'pyproject.toml')) && existsSync(join(dir, 'core'))) return dir;
		const up = dirname(dir);
		if (up === dir) throw new Error('JobHunter root not found (set JOBHUNTER_ROOT)');
		dir = up;
	}
}

export const ROOT = findRoot();
export const OUTPUT_DIR = join(ROOT, 'output');
const DB_PATH = process.env.JOBHUNTER_DB ? resolve(process.env.JOBHUNTER_DB) : join(ROOT, 'data', 'jobhunter.db');

let db: Database.Database | undefined;

export function getDb(): Database.Database {
	if (!db) {
		if (!existsSync(DB_PATH)) throw new Error(`${DB_PATH} not found — run: uv run python cli.py init-db`);
		db = new Database(DB_PATH);
		db.pragma('journal_mode = WAL');
		db.pragma('foreign_keys = ON');
		db.pragma('busy_timeout = 30000');
	}
	return db;
}

// ── jobs ────────────────────────────────────────────────────────────────────

export type JobQuery = {
	status?: string; source?: string; work_mode?: string; q?: string; excludeSkipped?: boolean;
	favorites?: boolean; sort?: string; dir?: 'asc' | 'desc'; page?: number; pageSize?: number;
};

/** Sortable columns (whitelist → SQL). NULL fit scores always go last. */
export const SORTS: Record<string, string> = {
	title: 'title COLLATE NOCASE',
	company: 'company COLLATE NOCASE',
	location: 'location COLLATE NOCASE',
	work_mode: 'work_mode',
	fit: 'fit_score',
	status: 'status',
	first_seen: 'first_seen_at'
};
export const PAGE_SIZES = [25, 50, 100];

/** One page of jobs plus the total count for the pager. */
export function listJobs(f: JobQuery) {
	const where: string[] = [];
	const args: unknown[] = [];
	if (f.status) { where.push('status = ?'); args.push(f.status); }
	else if (f.excludeSkipped) where.push("status != 'skipped'");
	if (f.favorites) where.push('favorite = 1');
	if (f.source) { where.push('source = ?'); args.push(f.source); }
	if (f.work_mode) { where.push("COALESCE(work_mode, 'unknown') = ?"); args.push(f.work_mode); }
	if (f.q) {
		where.push('(title LIKE ? OR company LIKE ? OR location LIKE ?)');
		const like = `%${f.q}%`;
		args.push(like, like, like);
	}
	const whereSql = where.length ? 'WHERE ' + where.join(' AND ') : '';
	const col = SORTS[f.sort ?? ''] ?? SORTS.first_seen;
	const dir = f.dir === 'asc' ? 'ASC' : 'DESC';
	const pageSize = PAGE_SIZES.includes(f.pageSize ?? 0) ? f.pageSize! : 50;
	const total = (getDb().prepare(`SELECT COUNT(*) n FROM jobs ${whereSql}`).get(...args) as any).n as number;
	const pages = Math.max(1, Math.ceil(total / pageSize));
	const page = Math.min(Math.max(1, f.page ?? 1), pages);
	const sql = `SELECT j.id, title, company, location, work_mode, fit_score, status, attention_reason,
	                    source, salary_flag, first_seen_at, docs_requested, favorite,
	                    (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.id
	                       AND (a.cv_path IS NOT NULL OR a.letter_path IS NOT NULL)) AS has_docs
	             FROM jobs j ${whereSql}
	             ORDER BY (${col}) IS NULL, ${col} ${dir}, j.id DESC LIMIT ? OFFSET ?`;
	const rows = getDb().prepare(sql).all(...args, pageSize, (page - 1) * pageSize) as any[];
	return { rows, total, page, pages, pageSize };
}

export const DOC_CHOICES = {
	cv: 'CV only', both: 'CV + cover letter', letter: 'Cover letter only', motivation: 'Motivationsschreiben (extra, on request)'
} as const;

/** The setting default_documents: what runs write when the user didn't pick per job. Mirrors core/jobs. */
export function defaultDocuments(): 'cv' | 'both' {
	return getSettings().default_documents === 'both' ? 'both' : 'cv';
}
const REQUESTABLE = ['new', 'skipped', 'shortlisted', 'needs_attention', 'docs_ready'];

/** "Apply anyway" / "Write documents": the next writer stage (or "Generate now") tailors this job
 *  regardless of its fit score. Mirrors core/jobs.request_documents. */
export function requestDocuments(jobId: number, which: string) {
	if (!(which in DOC_CHOICES)) throw new Error('choose CV, cover letter, both or Motivationsschreiben');
	const d = getDb();
	d.transaction(() => {
		const job = d.prepare('SELECT status FROM jobs WHERE id = ?').get(jobId) as any;
		if (!job) throw new Error(`job ${jobId} not found`);
		if (!REQUESTABLE.includes(job.status)) throw new Error(`documents can't be requested for a job with status ${job.status}`);
		d.prepare("UPDATE jobs SET docs_requested = ?, updated_at = datetime('now') WHERE id = ?").run(which, jobId);
		setStatus(jobId, 'shortlisted', `documents requested: ${DOC_CHOICES[which as keyof typeof DOC_CHOICES]}`);
	})();
}

/** ☆/★: the user's favourites (migration 011); the Jobs list can show only these. */
export function toggleFavorite(jobId: number): boolean {
	const r = getDb().prepare('UPDATE jobs SET favorite = 1 - favorite WHERE id = ? RETURNING favorite').get(jobId) as any;
	if (!r) throw new Error(`job ${jobId} not found`);
	return !!r.favorite;
}

/** The user's own notes on the application process (migration 017). Empty text clears them. */
export const MAX_USER_NOTES = 20_000;
export function saveUserNotes(jobId: number, text: string) {
	const notes = text.replace(/\r\n/g, '\n').trim();
	if (notes.length > MAX_USER_NOTES) throw new Error(`notes are longer than ${MAX_USER_NOTES} characters`);
	const r = getDb().prepare("UPDATE jobs SET user_notes = ?, user_notes_at = CASE WHEN ? IS NULL THEN NULL ELSE datetime('now') END WHERE id = ?")
		.run(notes || null, notes || null, jobId);
	if (!r.changes) throw new Error(`job ${jobId} not found`);
}

export function favoriteCount(): number {
	return (getDb().prepare('SELECT COUNT(*) n FROM jobs WHERE favorite = 1').get() as any).n;
}

export function requestedCount(): number {
	return (getDb().prepare("SELECT COUNT(*) n FROM jobs WHERE status = 'shortlisted' AND docs_requested IS NOT NULL").get() as any).n;
}

export function statusCounts(): Record<string, number> {
	const rows = getDb().prepare('SELECT status, COUNT(*) n FROM jobs GROUP BY status').all() as any[];
	return Object.fromEntries(rows.map((r) => [r.status, r.n]));
}

/** Jobs that need a decision; alert jobs waiting for review are counted separately (reviewCount). */
export function needsYouCount(): number {
	return (getDb().prepare("SELECT COUNT(*) n FROM jobs WHERE status = 'needs_attention' AND attention_reason IS NOT 'alert_review'").get() as any).n;
}

export function reviewCount(): number {
	return (getDb().prepare("SELECT COUNT(*) n FROM jobs WHERE status = 'needs_attention' AND attention_reason = 'alert_review'").get() as any).n;
}

/** Job-alert jobs that match no filter (user request 2026-10-18): the user picks which to evaluate. */
export function reviewJobs() {
	return getDb()
		.prepare(`SELECT id, title, company, location, work_mode, url, posted_at, first_seen_at FROM jobs
		          WHERE status = 'needs_attention' AND attention_reason = 'alert_review'
		          ORDER BY first_seen_at DESC, id DESC`)
		.all() as any[];
}

/** Bulk decision on review jobs: 'new' (the next run, or "Score waiting jobs", evaluates them) or 'skipped'. */
export function decideReview(ids: number[], to: 'new' | 'skipped'): number {
	const d = getDb();
	let n = 0;
	d.transaction(() => {
		const job = d.prepare("SELECT status, attention_reason FROM jobs WHERE id = ?");
		for (const id of ids) {
			const j = job.get(id) as any;
			if (!j || j.status !== 'needs_attention' || j.attention_reason !== 'alert_review') continue;
			d.prepare("UPDATE jobs SET status = ?, attention_reason = NULL, updated_at = datetime('now') WHERE id = ?").run(to, id);
			d.prepare("INSERT INTO status_history (job_id, from_status, to_status, note, changed_by) VALUES (?, 'needs_attention', ?, ?, 'user')")
				.run(id, to, to === 'new' ? 'alert review: evaluate it' : 'alert review: not interested');
			n++;
		}
	})();
	return n;
}

export function getJob(id: number) {
	const job = getDb().prepare('SELECT * FROM jobs WHERE id = ?').get(id) as any;
	if (job) job.project_suggestions = JSON.parse(job.project_suggestions || '[]');
	return job;
}

export function getApplication(jobId: number) {
	const a = getDb().prepare('SELECT * FROM applications WHERE job_id = ?').get(jobId) as any;
	if (a) a.inferred_facts = JSON.parse(a.inferred_facts || '[]');
	return a;
}

export function getHistory(jobId: number) {
	return getDb()
		.prepare('SELECT from_status, to_status, note, changed_by, changed_at FROM status_history WHERE job_id = ? ORDER BY id DESC')
		.all(jobId) as any[];
}

export function attentionJobs() {
	const rows = getDb()
		.prepare(`SELECT j.id, j.title, j.company, j.location, j.attention_reason, j.fit_score, j.updated_at,
		                 (SELECT note FROM status_history h WHERE h.job_id = j.id AND h.to_status = 'needs_attention'
		                  ORDER BY h.id DESC LIMIT 1) AS detail
		          FROM jobs j WHERE j.status = 'needs_attention' AND j.attention_reason IS NOT 'alert_review'
		          ORDER BY j.updated_at DESC`)
		.all() as any[];
	for (const r of rows) {
		if (r.attention_reason === 'inferred_facts') r.inferred = getApplication(r.id)?.inferred_facts ?? [];
	}
	return rows;
}

/** Every user status change writes status_history with changed_by = 'user' (CLAUDE.md §4). */
export function setStatus(jobId: number, to: string, note: string | null) {
	if (!(USER_SETTABLE as readonly string[]).includes(to)) throw new Error(`status ${to} can't be set here`);
	const d = getDb();
	d.transaction(() => {
		const job = d.prepare('SELECT status FROM jobs WHERE id = ?').get(jobId) as any;
		if (!job) throw new Error(`job ${jobId} not found`);
		d.prepare("UPDATE jobs SET status = ?, attention_reason = NULL, updated_at = datetime('now') WHERE id = ?").run(to, jobId);
		d.prepare("INSERT INTO status_history (job_id, from_status, to_status, note, changed_by) VALUES (?, ?, ?, ?, 'user')")
			.run(jobId, job.status, to, note || null);
	})();
}

/** Apply kit: the live form demands unrestricted work authorization (§5a, §13). The user answers
 *  those questions personally; the job waits in needs_attention with that reason. */
export function flagWorkAuthorization(jobId: number, wording: string | null) {
	const d = getDb();
	d.transaction(() => {
		const job = d.prepare('SELECT status FROM jobs WHERE id = ?').get(jobId) as any;
		if (!job) throw new Error(`job ${jobId} not found`);
		d.prepare("UPDATE jobs SET status = 'needs_attention', attention_reason = 'work_authorization', updated_at = datetime('now') WHERE id = ?").run(jobId);
		d.prepare("INSERT INTO status_history (job_id, from_status, to_status, note, changed_by) VALUES (?, ?, 'needs_attention', ?, 'user')")
			.run(jobId, job.status, `work_authorization: form demands${wording ? ` "${wording}"` : ' unrestricted work authorization'}`);
	})();
}

export function notInterested(jobId: number, note: string | null) {
	setStatus(jobId, 'skipped', note ? `not interested: ${note}` : 'not interested');
}

export function markApplied(jobId: number, note: string | null) {
	const d = getDb();
	d.transaction(() => {
		d.prepare(`INSERT INTO applications (job_id, applied_at) VALUES (?, datetime('now'))
		           ON CONFLICT(job_id) DO UPDATE SET applied_at = datetime('now')`).run(jobId);
		setStatus(jobId, 'applied', note || 'applied');
	})();
}

/** R5/R9: the user accepts the inferred facts → the documents may be used. */
export function approveInferred(jobId: number) {
	const d = getDb();
	d.transaction(() => {
		const r = d.prepare("UPDATE applications SET inferred_approved_at = datetime('now') WHERE job_id = ?").run(jobId);
		if (r.changes === 0) throw new Error(`job ${jobId} has no application`);
		setStatus(jobId, 'docs_ready', 'inferred facts approved');
	})();
}

/** The user rejects them → remembered in rejected_inferences (R9: never reused), job back to
 *  shortlisted so the next run re-renders without them. Mirrors core/applications.reject_inferred. */
export function rejectInferred(jobId: number, note: string | null) {
	const d = getDb();
	d.transaction(() => {
		const app = getApplication(jobId);
		if (!app) throw new Error(`job ${jobId} has no application`);
		const ins = d.prepare('INSERT INTO rejected_inferences (text, basis, job_id) VALUES (?, ?, ?)');
		for (const f of app.inferred_facts) ins.run(f.text, f.basis ?? null, jobId);
		setStatus(jobId, 'shortlisted', `inferred facts rejected${note ? ': ' + note : ''} — re-render without them`);
	})();
}

// ── filters ─────────────────────────────────────────────────────────────────

const JSON_FIELDS = ['keywords', 'exclude_keywords', 'work_modes', 'employment_types', 'languages', 'sources'];

export function listFilters() {
	return (getDb().prepare('SELECT * FROM search_filters ORDER BY id').all() as any[]).map(parseFilter);
}

export function getFilter(id: number) {
	const f = getDb().prepare('SELECT * FROM search_filters WHERE id = ?').get(id);
	return f ? parseFilter(f) : undefined;
}

function parseFilter(f: any) {
	for (const k of JSON_FIELDS) f[k] = JSON.parse(f[k] || '[]');
	f.active = !!f.active;
	f.exclude_freelance = !!f.exclude_freelance;
	return f;
}

export type FilterInput = {
	name: string; active: boolean; keywords: string[]; exclude_keywords: string[];
	location: string | null; radius_km: number; work_modes: string[]; employment_types: string[];
	exclude_freelance: boolean; languages: string[]; sources: string[]; max_age_days: number; min_fit_score: number;
};

export function saveFilter(id: number | null, f: FilterInput): number {
	const v = {
		...f,
		active: f.active ? 1 : 0,
		exclude_freelance: f.exclude_freelance ? 1 : 0,
		...Object.fromEntries(JSON_FIELDS.map((k) => [k, JSON.stringify((f as any)[k])]))
	};
	const cols = Object.keys(v);
	const d = getDb();
	if (id === null) {
		const r = d.prepare(`INSERT INTO search_filters (${cols.join(', ')}) VALUES (${cols.map((c) => '@' + c).join(', ')})`).run(v);
		return Number(r.lastInsertRowid);
	}
	d.prepare(`UPDATE search_filters SET ${cols.map((c) => `${c} = @${c}`).join(', ')}, updated_at = datetime('now') WHERE id = @id`)
		.run({ ...v, id });
	return id;
}

export function toggleFilter(id: number) {
	getDb().prepare("UPDATE search_filters SET active = 1 - active, updated_at = datetime('now') WHERE id = ?").run(id);
}

/** Jobs keep their history; their filter reference is cleared first (foreign key). */
export function deleteFilter(id: number) {
	const d = getDb();
	d.transaction(() => {
		d.prepare('UPDATE jobs SET filter_id = NULL WHERE filter_id = ?').run(id);
		d.prepare('DELETE FROM search_filters WHERE id = ?').run(id);
	})();
}

// ── statistics (/stats) ─────────────────────────────────────────────────────

export type StatsPeriod = 'day' | 'month';

/** Per day (last 30) or month (last 12), in local time: jobs found and scored, and the pipeline
 *  steps (documents ready, applied, interview/offer, rejected/withdrawn) from status_history.
 *  Each job counts once per period and step. Missing periods are filled with 0. */
export function stats(period: StatsPeriod) {
	const fmt = period === 'day' ? '%Y-%m-%d' : '%Y-%m';
	const since = period === 'day' ? "date('now', 'localtime', '-29 days')" : "date('now', 'localtime', 'start of month', '-11 months')";
	const d = getDb();
	const count = (sql: string) =>
		Object.fromEntries((d.prepare(sql).all() as any[]).map((r) => [r.p, r.n])) as Record<string, number>;
	const hist = (where: string) => count(
		`SELECT strftime('${fmt}', changed_at, 'localtime') p, COUNT(DISTINCT job_id) n FROM status_history
		 WHERE date(changed_at, 'localtime') >= ${since} AND (${where}) GROUP BY p`);
	const series = {
		found: count(`SELECT strftime('${fmt}', first_seen_at, 'localtime') p, COUNT(*) n FROM jobs
		              WHERE date(first_seen_at, 'localtime') >= ${since} GROUP BY p`),
		scored: hist("changed_by = 'claude' AND ((from_status = 'new' AND to_status IN ('shortlisted', 'skipped')) OR note LIKE 'scored: fit %')"),
		docs: hist("changed_by = 'claude' AND to_status = 'docs_ready' AND from_status IS NOT to_status"),
		applied: hist("to_status = 'applied' AND from_status IS NOT 'applied'"),
		interview: hist("to_status IN ('interview', 'offer') AND from_status IS NOT to_status"),
		rejected: hist("to_status IN ('rejected', 'withdrawn') AND from_status IS NOT to_status"),
		// one series per status, for the small multiples
		shortlisted: hist("to_status = 'shortlisted' AND from_status IS NOT 'shortlisted'"),
		skipped_fit: hist("to_status = 'skipped' AND changed_by = 'claude'"),
		not_interested: hist("to_status = 'skipped' AND changed_by = 'user'"),
		flagged: hist(`to_status = 'needs_attention' AND from_status IS NOT 'needs_attention'
		               AND COALESCE(note, '') NOT LIKE 'alert_review%' AND COALESCE(note, '') NOT LIKE 'alert re-parsed%'`),
		review: hist("to_status = 'needs_attention' AND (note LIKE 'alert_review%' OR note LIKE 'alert re-parsed%')"),
		feedback: hist("to_status = 'feedback' AND from_status IS NOT 'feedback'"),
		interview_only: hist("to_status = 'interview' AND from_status IS NOT 'interview'"),
		offer: hist("to_status = 'offer' AND from_status IS NOT 'offer'"),
		rejected_only: hist("to_status = 'rejected' AND from_status IS NOT 'rejected'"),
		withdrawn: hist("to_status = 'withdrawn' AND from_status IS NOT 'withdrawn'")
	};
	// all periods in range, oldest first
	const periods: string[] = [];
	const now = new Date();
	for (let i = period === 'day' ? 29 : 11; i >= 0; i--) {
		const t = period === 'day' ? new Date(now.getFullYear(), now.getMonth(), now.getDate() - i) : new Date(now.getFullYear(), now.getMonth() - i, 1);
		const y = t.getFullYear(), m = String(t.getMonth() + 1).padStart(2, '0'), day = String(t.getDate()).padStart(2, '0');
		periods.push(period === 'day' ? `${y}-${m}-${day}` : `${y}-${m}`);
	}
	const rows = periods.map((p) => ({
		period: p,
		...Object.fromEntries(Object.entries(series).map(([k, v]) => [k, v[p] ?? 0]))
	})) as ({ period: string } & Record<keyof typeof series, number>)[];
	return { period, rows };
}

// ── applications (/applications, follow-ups; mirrors core/followups.py) ──────

// The date the user applied: "Mark as applied", else the first status change to applied.
const APPLIED_AT = `COALESCE(a.applied_at, (SELECT MIN(h.changed_at) FROM status_history h
                                           WHERE h.job_id = j.id AND h.to_status = 'applied'))`;
export const APPLIED_STATUSES = ['applied', 'feedback', 'interview', 'offer', 'rejected', 'withdrawn'];

/** Jobs the user applied to, newest first; `from`/`to` = local dates YYYY-MM-DD (inclusive). */
export function applicationList(from?: string | null, to?: string | null, jobId?: number) {
	const where = ['applied_at IS NOT NULL'];
	const args: unknown[] = [];
	if (from) { where.push(`date(applied_at, 'localtime') >= ?`); args.push(from); }
	if (to) { where.push(`date(applied_at, 'localtime') <= ?`); args.push(to); }
	if (jobId) { where.push('id = ?'); args.push(jobId); }
	return getDb().prepare(
		`SELECT * FROM (
		   SELECT j.id, j.title, j.company, j.location, j.url, j.apply_url, j.apply_email, j.apply_method, j.source,
		          j.status, a.method, a.followup_reminded_at, a.followed_up_at, a.no_response_reminded_at,
		          ${APPLIED_AT} AS applied_at,
		          CAST(julianday('now') - julianday(${APPLIED_AT}) AS INTEGER) AS days,
		          (SELECT MAX(h.changed_at) FROM status_history h WHERE h.job_id = j.id AND h.to_status = j.status
		             AND h.from_status IS NOT h.to_status) AS status_at
		   FROM jobs j LEFT JOIN applications a ON a.job_id = j.id
		   WHERE j.status IN (${APPLIED_STATUSES.map(() => '?').join(', ')})
		 ) WHERE ${where.join(' AND ')}
		 ORDER BY applied_at DESC`
	).all(...APPLIED_STATUSES, ...args) as any[];
}

/** Follow-up state of a job still waiting for a reply (status applied), else null. */
export function followupState(jobId: number) {
	const row = applicationList(null, null, jobId)[0];
	if (!row || row.status !== 'applied') return null;
	const s = getSettings();
	const after = Math.trunc(Number(s.followup_after_days ?? 14)) || 0;
	const silent = Math.trunc(Number(s.followup_no_response_days ?? 42)) || 0;
	return {
		days: row.days as number, appliedAt: row.applied_at as string, followedUpAt: row.followed_up_at as string | null,
		after, silent,
		due: !!after && row.days >= after && !row.followed_up_at,
		noResponse: !!silent && row.days >= silent
	};
}

// ── job boards (bookmarks, migration 012) ───────────────────────────────────

const BOARD_URL = /^https?:\/\/\S+$/;

export function listBoards() {
	return getDb().prepare('SELECT * FROM job_boards ORDER BY name COLLATE NOCASE').all() as any[];
}

export function saveBoard(id: number | null, name: string, url: string, note: string | null) {
	name = name.trim();
	url = url.trim();
	if (!name) throw new Error('give the board a name');
	if (!BOARD_URL.test(url) || url.length > 2000) throw new Error('the link must start with http:// or https://');
	const d = getDb();
	if (id === null) d.prepare('INSERT INTO job_boards (name, url, note) VALUES (?, ?, ?)').run(name, url, note || null);
	else d.prepare('UPDATE job_boards SET name = ?, url = ?, note = ? WHERE id = ?').run(name, url, note || null, id);
}

export function deleteBoard(id: number) {
	getDb().prepare('DELETE FROM job_boards WHERE id = ?').run(id);
}

/** The board's link, and remember when it was last opened. */
export function openBoard(id: number): string | undefined {
	const row = getDb().prepare("UPDATE job_boards SET last_opened_at = datetime('now') WHERE id = ? RETURNING url").get(id) as any;
	return row?.url;
}

// ── runs + settings ─────────────────────────────────────────────────────────

export function listRuns(limit = 100) {
	return (getDb().prepare('SELECT * FROM runs ORDER BY id DESC LIMIT ?').all(limit) as any[]).map((r) => ({
		...r,
		errors: JSON.parse(r.errors || '[]'),
		source_searches: JSON.parse(r.source_searches || '{}')
	}));
}

export const SETTING_INFO: Record<string, { label: string; kind: 'int' | 'number' | 'bool' | 'text' | 'choice' | 'json'; options?: string[] }> = {
	model_filter: { label: 'Claude Code: model for searching, filtering and scoring', kind: 'choice', options: ['haiku', 'sonnet', 'opus'] },
	model_writer: { label: 'Claude Code: model for CVs and cover letters', kind: 'choice', options: ['sonnet', 'opus', 'haiku'] },
	llm_model_filter: { label: 'Other LLM provider (LLM_PROVIDER in .env): model id for searching and scoring', kind: 'text' },
	llm_model_writer: { label: 'Other LLM provider: model id for CVs and cover letters', kind: 'text' },
	default_documents: { label: 'Documents to write unless you pick per job (cv = CV only, both = CV + cover letter)', kind: 'choice', options: ['cv', 'both'] },
	min_fit_for_documents: { label: 'Write documents automatically from fit score', kind: 'int' },
	max_tailored_per_run: { label: 'Max. jobs tailored per run', kind: 'int' },
	max_evaluated_per_run: { label: 'Max. new jobs evaluated per run', kind: 'int' },
	search_limit_per_source: { label: 'Postings per source per filter', kind: 'int' },
	min_hours_between_runs: { label: 'Min. hours between runs', kind: 'number' },
	job_retention_days: { label: 'Delete untouched jobs after … days (0 = never; applied, documents and ★ favourites are always kept)', kind: 'int' },
	telegram_enabled: { label: 'Telegram notifications (master switch)', kind: 'bool' },
	notify_docs_ready: { label: 'Telegram: documents written (every run, incl. Generate now)', kind: 'bool' },
	notify_evaluated: { label: 'Telegram: result of "Evaluate now" / "Re-evaluate"', kind: 'bool' },
	notify_run_summary: { label: 'Telegram: summary of scheduled runs (+ new shortlisted jobs)', kind: 'bool' },
	notify_attention: { label: 'Telegram: jobs that need you', kind: 'bool' },
	notify_failures: { label: 'Telegram: failed runs, source errors, runs that could not start', kind: 'bool' },
	notify_followups: { label: 'Telegram: follow-up reminders for applications without a reply', kind: 'bool' },
	followup_after_days: { label: 'Follow-up reminder after … days without a reply (0 = off)', kind: 'int' },
	followup_no_response_days: { label: '"No reply" reminder after … days (suggests rejected/withdrawn; 0 = off)', kind: 'int' },
	work_permit_checks: { label: 'I need a work permit: flag jobs below the Blue Card salary or demanding unrestricted work authorization (off = EU citizens)', kind: 'bool' },
	blue_card_salary_min: { label: 'Blue Card salary threshold (€ gross/year)', kind: 'number' },
	blue_card_salary_year: { label: 'Blue Card threshold year', kind: 'int' },
	ui_base_url: { label: 'UI base URL (links in Telegram)', kind: 'text' },
	alert_senders: { label: 'Job-alert senders (JSON list of {board, from}; board = linkedin | instaffo | stepstone | xing)', kind: 'json' },
	alert_folder: { label: 'Mail folder with the job alerts', kind: 'text' }
};

/** How many jobs the automatic clean-up would delete now (mirrors core/jobs.purge_old_jobs). */
export function purgePreview(): { days: number; count: number } {
	const days = Math.trunc(Number(getSettings().job_retention_days ?? 0)) || 0;
	if (days <= 0) return { days: 0, count: 0 };
	const n = (getDb().prepare(`SELECT COUNT(*) n FROM jobs
		WHERE status IN ('new', 'skipped', 'shortlisted', 'needs_attention') AND favorite = 0
		  AND docs_requested IS NULL AND id NOT IN (SELECT job_id FROM applications)
		  AND updated_at < datetime('now', ?)`).get(`-${days} days`) as any).n;
	return { days, count: n };
}

export function getSettings(): Record<string, string> {
	const rows = getDb().prepare('SELECT key, value FROM settings').all() as any[];
	return Object.fromEntries(rows.map((r) => [r.key, r.value]));
}

export function updateSettings(values: Record<string, string>) {
	const d = getDb();
	const stmt = d.prepare('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value');
	d.transaction(() => {
		for (const [k, v] of Object.entries(values)) {
			if (!(k in SETTING_INFO)) throw new Error(`unknown setting ${k}`);
			stmt.run(k, v);
		}
	})();
}
