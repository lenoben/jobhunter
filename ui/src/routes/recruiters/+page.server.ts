import { fail } from '@sveltejs/kit';
import { detectedRecruiterJobs, listRecruiters } from '$lib/server/db';
import { cli } from '$lib/server/python';

export function load() {
	return { recruiters: listRecruiters(), detected: detectedRecruiterJobs() };
}

function id(f: FormData) {
	const v = Number(f.get('id'));
	return Number.isInteger(v) && v > 0 ? v : null;
}

/** "Hays, Hays AG, Hays Talent Solutions" (or one per line) → the names to match. */
function names(f: FormData): string[] {
	return String(f.get('names') ?? '').split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
}

/** Adding, editing and removing go through the Python CLI (core/recruiters.py), where the
 *  company matching lives, so it exists only once; it tags/untags the stored jobs at once. */
export const actions = {
	add: async ({ request }) => {
		const f = await request.formData();
		const n = names(f), note = String(f.get('note') ?? '').trim();
		if (!n.length) return fail(400, { error: 'Enter the recruiter’s name.', values: { names: '', note } });
		const r = cli(['recruiters', 'add', ...n.flatMap((x) => ['--name', x]), ...(note ? ['--note', note] : [])]);
		if (r.error) return fail(400, { error: r.error, values: { names: n.join(', '), note } });
		return { added: { name: r.names[0] as string, tagged: r.tagged as { id: number; title: string; company: string; status: string }[] } };
	},
	update: async ({ request }) => {
		const f = await request.formData();
		const rid = id(f);
		if (rid === null) return fail(400, { error: 'bad id' });
		const note = String(f.get('note') ?? '').trim();
		const r = cli(['recruiters', 'update', '--id', String(rid), ...names(f).flatMap((x) => ['--name', x]), '--note', note]);
		if (r.error) return fail(400, { error: r.error, editing: rid });
		return { updated: { name: r.names[0] as string, tagged: r.tagged.length as number } };
	},
	remove: async ({ request }) => {
		const rid = id(await request.formData());
		if (rid === null) return fail(400, { error: 'bad id' });
		const r = cli(['recruiters', 'remove', '--id', String(rid)]);
		if (r.error) return fail(400, { error: r.error });
		return { removed: r.untagged as number };
	},
	/** From the "found by the scoring model" list: not a recruiter after all. */
	clear: async ({ request }) => {
		const jid = Number((await request.formData()).get('job'));
		if (!Number.isInteger(jid) || jid <= 0) return fail(400, { error: 'bad job id' });
		const r = cli(['recruiters', 'clear-job', '--job', String(jid)]);
		if (r.error) return fail(400, { error: r.error });
		return { cleared: true };
	}
};
