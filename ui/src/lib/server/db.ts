// Server-only DB access for the UI (CLAUDE.md §12). Same SQLite file as the Python core; the
// schema is owned by core/migrations (Python) — this module never changes it.
import Database from 'better-sqlite3';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

export const STATUSES = [
	'new', 'skipped', 'shortlisted', 'docs_ready', 'needs_attention',
	'applied', 'interview', 'offer', 'rejected', 'withdrawn'
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
	sort?: string; dir?: 'asc' | 'desc'; page?: number; pageSize?: number;
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
	                    source, salary_flag, first_seen_at, docs_requested,
	                    (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.id
	                       AND (a.cv_path IS NOT NULL OR a.letter_path IS NOT NULL)) AS has_docs
	             FROM jobs j ${whereSql}
	             ORDER BY (${col}) IS NULL, ${col} ${dir}, j.id DESC LIMIT ? OFFSET ?`;
	const rows = getDb().prepare(sql).all(...args, pageSize, (page - 1) * pageSize) as any[];
	return { rows, total, page, pages, pageSize };
}

export const DOC_CHOICES = { both: 'CV + cover letter', cv: 'CV only', letter: 'Cover letter only' } as const;
const REQUESTABLE = ['new', 'skipped', 'shortlisted', 'needs_attention', 'docs_ready'];

/** "Apply anyway" / "Write documents": the next writer stage (or "Generate now") tailors this job
 *  regardless of its fit score. Mirrors core/jobs.request_documents. */
export function requestDocuments(jobId: number, which: string) {
	if (!(which in DOC_CHOICES)) throw new Error('choose CV, cover letter or both');
	const d = getDb();
	d.transaction(() => {
		const job = d.prepare('SELECT status FROM jobs WHERE id = ?').get(jobId) as any;
		if (!job) throw new Error(`job ${jobId} not found`);
		if (!REQUESTABLE.includes(job.status)) throw new Error(`documents can't be requested for a job with status ${job.status}`);
		d.prepare("UPDATE jobs SET docs_requested = ?, updated_at = datetime('now') WHERE id = ?").run(which, jobId);
		setStatus(jobId, 'shortlisted', `documents requested: ${DOC_CHOICES[which as keyof typeof DOC_CHOICES]}`);
	})();
}

export function requestedCount(): number {
	return (getDb().prepare("SELECT COUNT(*) n FROM jobs WHERE status = 'shortlisted' AND docs_requested IS NOT NULL").get() as any).n;
}

export function statusCounts(): Record<string, number> {
	const rows = getDb().prepare('SELECT status, COUNT(*) n FROM jobs GROUP BY status').all() as any[];
	return Object.fromEntries(rows.map((r) => [r.status, r.n]));
}

export function needsYouCount(): number {
	return (getDb().prepare("SELECT COUNT(*) n FROM jobs WHERE status = 'needs_attention'").get() as any).n;
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
		          FROM jobs j WHERE j.status = 'needs_attention' ORDER BY j.updated_at DESC`)
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

// ── runs + settings ─────────────────────────────────────────────────────────

export function listRuns(limit = 100) {
	return (getDb().prepare('SELECT * FROM runs ORDER BY id DESC LIMIT ?').all(limit) as any[]).map((r) => ({
		...r,
		errors: JSON.parse(r.errors || '[]'),
		source_searches: JSON.parse(r.source_searches || '{}')
	}));
}

export const SETTING_INFO: Record<string, { label: string; kind: 'int' | 'number' | 'bool' | 'text' | 'choice' | 'json'; options?: string[] }> = {
	model_filter: { label: 'Model for searching, filtering and scoring', kind: 'choice', options: ['haiku', 'sonnet', 'opus'] },
	model_writer: { label: 'Model for CVs and cover letters', kind: 'choice', options: ['sonnet', 'opus', 'haiku'] },
	min_fit_for_documents: { label: 'Write documents automatically from fit score', kind: 'int' },
	max_tailored_per_run: { label: 'Max. jobs tailored per run', kind: 'int' },
	max_evaluated_per_run: { label: 'Max. new jobs evaluated per run', kind: 'int' },
	search_limit_per_source: { label: 'Postings per source per filter', kind: 'int' },
	min_hours_between_runs: { label: 'Min. hours between runs', kind: 'number' },
	telegram_enabled: { label: 'Telegram notifications', kind: 'bool' },
	blue_card_salary_min: { label: 'Blue Card salary threshold (€ gross/year)', kind: 'number' },
	blue_card_salary_year: { label: 'Blue Card threshold year', kind: 'int' },
	ui_base_url: { label: 'UI base URL (links in Telegram)', kind: 'text' },
	alert_senders: { label: 'Job-alert senders (JSON list of {board, from}; board = linkedin | instaffo | stepstone | xing)', kind: 'json' },
	alert_folder: { label: 'Mail folder with the job alerts', kind: 'text' }
};

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
