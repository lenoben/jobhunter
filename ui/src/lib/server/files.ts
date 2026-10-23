// Files from output/<job_id>/ (read-only) and the "Run now" launcher.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { Marked } from 'marked';
import { OUTPUT_DIR, ROOT } from './db';

// The only files the UI ever serves (CLAUDE.md §12: only from output/<id>/): generated documents,
// named <First>_<Last>_<Job_title>_<Lebenslauf|Anschreiben|Motivationsschreiben|CV|Cover_Letter|
// Motivation_Letter>.pdf (core/applications.py),
// plus the legacy names from before 2026-10-16.
const LEGACY: Record<string, string> = { 'cv.pdf': 'CV / Lebenslauf', 'anschreiben.pdf': 'Anschreiben', 'cover_letter.pdf': 'Cover letter' };
type DocKind = 'cv' | 'letter' | 'motivation';
const SUFFIXES: [string, string, DocKind][] = [
	['_Lebenslauf.pdf', 'Lebenslauf', 'cv'], ['_CV.pdf', 'CV', 'cv'],
	['_Anschreiben.pdf', 'Anschreiben', 'letter'], ['_Cover_Letter.pdf', 'Cover letter', 'letter'],
	['_Motivationsschreiben.pdf', 'Motivationsschreiben', 'motivation'], ['_Motivation_Letter.pdf', 'Motivation letter', 'motivation']
];
const ORDER: Record<DocKind, number> = { cv: 0, letter: 1, motivation: 2 };
const SAFE_NAME = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,200}\.pdf$/;

/** { label, kind } if `name` is a generated document's file name, else null. */
export function classifyDocument(name: string): { label: string; kind: DocKind } | null {
	if (name in LEGACY) return { label: LEGACY[name], kind: name === 'cv.pdf' ? 'cv' : 'letter' };
	if (!SAFE_NAME.test(name)) return null;
	const hit = SUFFIXES.find(([suffix]) => name.endsWith(suffix));
	return hit ? { label: hit[1], kind: hit[2] } : null;
}

export function jobDir(jobId: number): string {
	return join(OUTPUT_DIR, String(Math.trunc(jobId)));
}

/** Removes output/<id>/ (PDFs, content.json, notes.md) after the job was deleted. */
export function deleteJobFiles(jobId: number) {
	if (!Number.isInteger(jobId) || jobId <= 0) return;
	rmSync(jobDir(jobId), { recursive: true, force: true });
}

/** The job's documents: CV, letter, Motivationsschreiben. */
export function listDocuments(jobId: number) {
	const dir = jobDir(jobId);
	if (!existsSync(dir)) return [];
	return readdirSync(dir)
		.map((name) => ({ name, info: classifyDocument(name) }))
		.filter((d) => d.info)
		.sort((a, b) => ORDER[a.info!.kind] - ORDER[b.info!.kind] || a.name.localeCompare(b.name))
		.map((d) => ({ name: d.name, label: d.info!.label, path: join(dir, d.name) }));
}

/** Raw HTML in notes (job ads are third-party text) is shown as text, never rendered. */
const marked = new Marked({
	gfm: true,
	renderer: {
		html({ text }) {
			return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
		}
	}
});

export function markdown(text: string | null | undefined): string | null {
	return text ? (marked.parse(text) as string) : null;
}

export function notesHtml(jobId: number): string | null {
	const path = join(jobDir(jobId), 'notes.md');
	return existsSync(path) ? markdown(readFileSync(path, 'utf-8')) : null;
}

/** Start run.ps1 in the background. 'manual' = full run (time guard applies); 'docs' = "Generate now":
 *  writer only, for the jobs the user requested documents for (no time guard); 'single' = one job.
 *  Started through `cmd /c start`, so the run gets its own (hidden) console: it survives a restart of
 *  the UI and Ctrl+C in the UI's terminal. (spawn with detached: true starts PowerShell without a
 *  console, and it exits at once without running anything — that silently broke these buttons.) */
export function runNow(trigger: 'manual' | 'docs' | 'single' | 'evaluate' = 'manual', jobId?: number): string {
	const shell = spawnSync('where', ['pwsh'], { windowsHide: true }).status === 0 ? 'pwsh' : 'powershell.exe';
	const extra = trigger === 'single' && jobId ? ['-JobId', String(Math.trunc(jobId))] : [];
	const child = spawn('cmd.exe', ['/d', '/c', 'start', '"JobHunter"', '/min', shell, '-NoProfile', '-WindowStyle', 'Hidden',
		'-ExecutionPolicy', 'Bypass', '-File', join(ROOT, 'run.ps1'), '-Trigger', trigger, ...extra], {
		cwd: ROOT,
		stdio: 'ignore',
		windowsHide: true
	});
	child.unref();
	if (trigger === 'single') {
		return `Evaluating this job now. In 1–3 minutes it shows its fit score, and if it meets your criteria the documents too. Reload the page to see it; Telegram tells you when it's done.`;
	}
	if (trigger === 'evaluate') {
		return `Scoring up to 60 waiting jobs now (no new search), then writing documents for those that qualify. This takes 5–15 minutes; Telegram tells you when it's done.`;
	}
	return trigger === 'docs'
		? `Writing the requested documents now. This takes a few minutes per job; the job then shows "docs ready" (or "needs you"), and Telegram tells you when it's done.`
		: `Run started. It appears under Runs within a minute — unless the time guard refuses it.`;
}
