import { fail, redirect } from '@sveltejs/kit';
import { cli } from '$lib/server/python';
import {
	listJobs, notInterested, PAGE_SIZES, requestDocuments, requestedCount, SORTS, SOURCES, STATUSES, statusCounts
} from '$lib/server/db';
import { runNow } from '$lib/server/files';

export function load({ url }) {
	const p = url.searchParams;
	const status = p.get('status') || 'open';
	const sort = SORTS[p.get('sort') ?? ''] ? p.get('sort')! : 'first_seen';
	const dir = p.get('dir') === 'asc' ? 'asc' : 'desc';
	const result = listJobs({
		status: status !== 'all' && status !== 'open' ? status : undefined,
		excludeSkipped: status === 'open',
		source: p.get('source') || undefined,
		work_mode: p.get('work_mode') || undefined,
		q: p.get('q')?.trim() || undefined,
		sort, dir,
		page: Number(p.get('page')) || 1,
		pageSize: Number(p.get('size')) || 50
	});
	return {
		...result,
		counts: statusCounts(),
		requested: requestedCount(),
		params: {
			status, sort, dir,
			source: p.get('source') ?? '', work_mode: p.get('work_mode') ?? '', q: p.get('q') ?? ''
		},
		statuses: STATUSES,
		sources: SOURCES,
		pageSizes: PAGE_SIZES
	};
}

function id(form: FormData) {
	const v = Number(form.get('id'));
	return Number.isInteger(v) && v > 0 ? v : null;
}

export const actions = {
	/** "Not interested": job → skipped, changed_by = 'user'. */
	skip: async ({ request }) => {
		const j = id(await request.formData());
		if (j === null) return fail(400, { error: 'bad id' });
		try {
			notInterested(j, null);
		} catch (e) {
			return fail(400, { error: (e as Error).message });
		}
		return { skipped: j };
	},
	/** "Apply anyway" / "Write documents" from the list: CV + cover letter in the next run. */
	docs: async ({ request }) => {
		const j = id(await request.formData());
		if (j === null) return fail(400, { error: 'bad id' });
		try {
			requestDocuments(j, 'both');
		} catch (e) {
			return fail(400, { error: (e as Error).message });
		}
		return { requested: j };
	},
	/** "Generate now": write the requested documents right away. */
	generate: async () => ({ started: runNow('docs') }),
	/** "Add a job": link (+ optional pasted posting). Evaluated now if asked; else in the next run. */
	add: async ({ request }) => {
		const f = await request.formData();
		const url = String(f.get('url') ?? '').trim();
		const text = String(f.get('text') ?? '').trim();
		const args = ['add-job', '--url', url];
		for (const k of ['title', 'company', 'location']) {
			const v = String(f.get(k) ?? '').trim();
			if (v) args.push(`--${k}`, v);
		}
		const r = cli(args, text || null);
		if (r.error) return fail(400, { addError: r.error, addValues: { url, text } });
		const evaluate = f.get('now') === 'on' && r.status === 'new';
		const started = evaluate ? runNow('single', r.job_id) : null;
		redirect(303, `/jobs/${r.job_id}?added=${r.created ? 'new' : 'existing'}${started ? '&evaluating=1' : ''}`);
	}
};
