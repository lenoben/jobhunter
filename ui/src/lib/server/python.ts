// Calls the Python CLI for operations whose logic lives in core/ (fetching a posting, dedup, §5a
// screening), so it exists only once. Pasted text goes through a temp file, never the command line.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ROOT } from './db';

function uvPath(): string {
	const local = join(process.env.USERPROFILE ?? '', '.local', 'bin', 'uv.exe');
	return existsSync(local) ? local : 'uv';
}

/** Runs `uv run python cli.py <args> --json`; `text` is passed as --text-file. */
export function cli(args: string[], text?: string | null): any {
	let dir: string | undefined;
	try {
		if (text) {
			dir = mkdtempSync(join(tmpdir(), 'jobhunter-'));
			const file = join(dir, 'posting.txt');
			writeFileSync(file, text, 'utf-8');
			args = [...args, '--text-file', file];
		}
		const r = spawnSync(uvPath(), ['run', 'python', 'cli.py', ...args, '--json'], {
			cwd: ROOT, encoding: 'utf-8', timeout: 90_000, windowsHide: true,
			env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
		});
		const line = (r.stdout ?? '').trim().split('\n').pop() ?? '';
		try {
			return JSON.parse(line);
		} catch {
			return { error: (r.stderr || r.stdout || r.error?.message || 'the Python CLI failed').toString().slice(-400) };
		}
	} finally {
		if (dir) rmSync(dir, { recursive: true, force: true });
	}
}
