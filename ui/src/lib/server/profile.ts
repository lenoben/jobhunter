// profile/profile.yaml for the UI: read it (apply kit, applications list) and edit it (/profile).
// Every save is checked by core/profile.py (`cli.py check-profile`) before it replaces the file,
// and the previous version is kept in profile/backups/ (last 20). Editing the motivation entries
// rewrites only that block, so the hand-written layout and comments elsewhere stay as they are.
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { parse } from 'yaml';
import { ROOT } from './db';
import { cli } from './python';

const KEEP_BACKUPS = 20;

export function profilePath(): string {
	return process.env.JOBHUNTER_PROFILE ?? join(ROOT, 'profile', 'profile.yaml');
}

export function loadProfile(): any {
	const path = profilePath();
	try {
		return existsSync(path) ? parse(readFileSync(path, 'utf-8')) ?? {} : {};
	} catch {
		return {};
	}
}

export function profileText(): string {
	const path = profilePath();
	return existsSync(path) ? readFileSync(path, 'utf-8') : '';
}

/** Motivation entries for the filter names (in that order), then any other existing keys. */
export function motivations(filterNames: string[]): { name: string; text: string; filter: boolean }[] {
	const m = loadProfile()?.motivation ?? {};
	const names = [...filterNames, ...Object.keys(m).filter((k) => !filterNames.includes(k))];
	return names.map((name) => ({ name, text: String(m[name] ?? '').trim(), filter: filterNames.includes(name) }));
}

export type SaveResult = { ok: true; warnings: string[]; backup: string | null } | { ok: false; error: string };

/** Validate `text` with core/profile.py; if it passes, back up the current file and replace it. */
export function saveProfileText(text: string): SaveResult {
	const path = profilePath();
	try {
		parse(text);
	} catch (e) {
		return { ok: false, error: `Not valid YAML: ${(e as Error).message.split('\n')[0]}` };
	}
	const tmp = `${path}.check.yaml`;
	mkdirSync(dirname(path), { recursive: true });
	writeFileSync(tmp, text, 'utf-8');
	try {
		const r = cli(['check-profile', '--path', tmp]);
		if (r.error) return { ok: false, error: r.error };
		let backup: string | null = null;
		if (existsSync(path)) {
			const dir = join(dirname(path), 'backups');
			mkdirSync(dir, { recursive: true });
			const stamp = new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15);
			backup = join(dir, `profile-${stamp}.yaml`);
			copyFileSync(path, backup);
			const old = readdirSync(dir).filter((f) => /^profile-\d{8}-\d{6}\.yaml$/.test(f)).sort();
			for (const f of old.slice(0, Math.max(0, old.length - KEEP_BACKUPS))) rmSync(join(dir, f));
		}
		renameSync(tmp, path);
		return { ok: true, warnings: r.warnings ?? [], backup };
	} finally {
		if (existsSync(tmp)) rmSync(tmp);
	}
}

const WRAP = 92;

function wrap(paragraph: string, indent: string): string[] {
	const lines: string[] = [];
	let line = '';
	for (const word of paragraph.split(/\s+/).filter(Boolean)) {
		if (line && indent.length + line.length + 1 + word.length > WRAP) {
			lines.push(indent + line);
			line = word;
		} else line = line ? `${line} ${word}` : word;
	}
	if (line) lines.push(indent + line);
	return lines;
}

/** The motivation block as the user writes it by hand: quoted keys, folded (>-) text wrapped at
 *  92 columns, a blank line between entries. A line break in the text becomes a paragraph. */
function motivationBlock(entries: [string, string][], keep: Map<string, string[]>): string {
	const out = ['motivation:'];
	entries.forEach(([name, raw], i) => {
		const paragraphs = raw.replace(/\r\n/g, '\n').split('\n').map((p) => p.trim()).filter(Boolean);
		if (i) out.push('');
		if (keep.has(name)) {
			out.push(...keep.get(name)!);
			return;
		}
		if (!paragraphs.length) {
			out.push(`  ${JSON.stringify(name)}: ""`);
			return;
		}
		out.push(`  ${JSON.stringify(name)}: >-`);
		paragraphs.forEach((p, j) => {
			if (j) out.push('');
			out.push(...wrap(p, '    '));
		});
	});
	return out.join('\n') + '\n';
}

const withoutMotivation = (p: any) => JSON.stringify({ ...(p ?? {}), motivation: undefined });
const normalise = (s: string) => s.replace(/\r\n/g, '\n').split('\n').map((p) => p.trim()).filter(Boolean).join('\n');

/** The original lines of each entry in the motivation block (lines[start] = "motivation:"), without
 *  the blank lines between entries. */
function entryLines(lines: string[], start: number, end: number): Map<string, string[]> {
	const out = new Map<string, string[]>();
	let key: string | null = null;
	for (const line of lines.slice(start + 1, end)) {
		const m = /^  ("(?:[^"\\]|\\.)*"|'[^']*'|[^\s#"'][^:]*):/.exec(line);
		if (m) {
			key = m[1].startsWith('"') ? JSON.parse(m[1]) : m[1].startsWith("'") ? m[1].slice(1, -1) : m[1].trim();
			out.set(key!, [line]);
		} else if (key) out.get(key)!.push(line);
	}
	for (const v of out.values()) while (v.length && !v.at(-1)!.trim()) v.pop();
	return out;
}

/** Set the motivation entries. Only the top-level `motivation:` block is rewritten (comments above
 *  it and the rest of the file stay byte for byte); refused if anything else would change. */
export function saveMotivations(entries: Record<string, string>): SaveResult {
	const text = profileText();
	let before: any;
	try {
		before = parse(text) ?? {};
	} catch (e) {
		return { ok: false, error: `profile.yaml is not valid YAML: ${(e as Error).message.split('\n')[0]}` };
	}
	const current: Record<string, unknown> = before.motivation && typeof before.motivation === 'object' ? before.motivation : {};
	const merged = new Map<string, string>(Object.entries(current).map(([k, v]) => [k, String(v ?? '')]));
	for (const [k, v] of Object.entries(entries)) merged.set(k, v);
	const lines = text.replace(/\r\n/g, '\n').split('\n');
	const start = lines.findIndex((l) => /^motivation\s*:\s*(#.*)?$/.test(l));
	if (start < 0 && lines.some((l) => /^["']?motivation["']?\s*:/.test(l))) {
		return { ok: false, error: 'motivation is not written as a block in profile.yaml; edit it under "Whole profile (YAML)"' };
	}
	let end = lines.findIndex((l, i) => i > start && /^[^\s#]/.test(l));
	if (end < 0) end = lines.length;
	// unchanged entries keep their original lines (wrapping, comments)
	const original = start < 0 ? new Map<string, string[]>() : entryLines(lines, start, end);
	const keep = new Map([...original].filter(([k]) => normalise(merged.get(k) ?? '') === normalise(String(current[k] ?? ''))));
	const block = motivationBlock([...merged.entries()], keep);

	let next: string;
	if (start < 0) {
		next = text.replace(/\n*$/, '\n\n') + block;
	} else {
		// comments and blank lines right above the next key belong to that key
		while (end - 1 > start && /^(#.*)?\s*$/.test(lines[end - 1])) end--;
		const tail = lines.slice(end);
		while (tail.length > 1 && !tail[0].trim()) tail.shift();
		next = [...lines.slice(0, start), block.replace(/\n$/, ''), ...(tail.length && tail.join('').trim() ? ['', ...tail] : [''])].join('\n');
	}
	let after: any;
	try {
		after = parse(next);
	} catch (e) {
		return { ok: false, error: `internal: the new motivation block is not valid YAML (${(e as Error).message.split('\n')[0]})` };
	}
	if (withoutMotivation(after) !== withoutMotivation(before)) {
		return { ok: false, error: 'internal: saving would have changed more than the motivation block; nothing was saved' };
	}
	for (const [k, v] of merged) {
		if (normalise(String(after.motivation?.[k] ?? '')) !== normalise(v)) {
			return { ok: false, error: `internal: the entry "${k}" would not read back as written; nothing was saved` };
		}
	}
	return saveProfileText(next);
}
