import { fail, redirect } from '@sveltejs/kit';
import { cli } from '$lib/server/python';
import {
	defaultDocuments, deleteJob, favoriteCount, getSettings, listJobs, notInterested, PAGE_SIZES, requestDocuments, requestedCount, SORTS, SOURCES, STATUSES,
	statusCounts, toggleFavorite
} from '$lib/server/db';
import { deleteJobFiles, runNow } from '$lib/server/files';

export function load({ url }) {
	const p = url.searchParams;
	const status = p.get('status') || 'open';
	const sort = SORTS[p.get('sort') ?? ''] ? p.get('sort')! : 'first_seen';
	const dir = p.get('dir') === 'asc' ? 'asc' : 'desc';
	const result = listJobs({
		status: status !== 'all' && status !== 'open' ? status : undefined,
		excludeSkipped: status === 'open',
		favorites: p.get('fav') === '1',
		source: p.get('source') || undefined,
		work_mode: p.get('work_mode') || undefined,
		q: p.get('q')?.trim() || undefined,
		sort, dir,
		page: Number(p.get('page')) || 1,
		pageSize: Number(p.get('size')) || 50
	});
	return {
		...result,
		deleted: p.get('deleted') === '1',
		counts: statusCounts(),
		requested: requestedCount(),
		favoriteCount: favoriteCount(),
		openAdd: p.get('add') === '1',
		maxEvaluated: Number(getSettings().max_evaluated_per_run ?? 30),
		params: {
			status, sort, dir, fav: p.get('fav') === '1' ? '1' : '',
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
	/** 🗑 from the list: delete the job and output/<id>/; only with confirm=yes (two-step button). */
	delete: async ({ request }) => {
		const f = await request.formData();
		const j = id(f);
		if (j === null) return fail(400, { error: 'bad id' });
		if (f.get('confirm') !== 'yes') return fail(400, { error: 'Delete was not confirmed' });
		if (!deleteJob(j)) return fail(404, { error: 'Job not found' });
		deleteJobFiles(j);
		return { deleted: j };
	},
	/** "Apply anyway" / "Write documents" from the list: the default documents (setting) in the next run. */
	docs: async ({ request }) => {
		const j = id(await request.formData());
		if (j === null) return fail(400, { error: 'bad id' });
		try {
			requestDocuments(j, defaultDocuments());
		} catch (e) {
			return fail(400, { error: (e as Error).message });
		}
		return { requested: j };
	},
	/** ☆/★ favourite. */
	favorite: async ({ request }) => {
		const j = id(await request.formData());
		if (j === null) return fail(400, { error: 'bad id' });
		try {
			return { favorite: toggleFavorite(j) };
		} catch (e) {
			return fail(400, { error: (e as Error).message });
		}
	},
	/** "Generate now": write the requested documents right away. */
	generate: async () => ({ started: runNow('docs') }),
	/** "Score waiting jobs": evaluate the backlog of new jobs (no search), then write documents. */
	score: async () => ({ started: runNow('evaluate') }),
	/** "Add a job": link (+ optional pasted posting). Evaluated now if asked; else in the next run. */
	add: async ({ request }) => {
		const f = await request.formData();
		const url = String(f.get('url') ?? '').trim();
		const text = String(f.get('text') ?? '').trim();
		const args = ['add-job', '--url', url];
		for (const k of ['title', 'company', 'location', 'apply-to']) {
			const v = String(f.get(k) ?? '').trim();
			if (v) args.push(`--${k}`, v);
		}
		const applyTo = String(f.get('apply-to') ?? '').trim();
		const r = cli(args, text || null);
		if (r.error) return fail(400, { addError: r.error, addValues: { url, text, applyTo } });
		const evaluate = f.get('now') === 'on' && r.status === 'new';
		const started = evaluate ? runNow('single', r.job_id) : null;
		redirect(303, `/jobs/${r.job_id}?added=${r.created ? 'new' : 'existing'}${started ? '&evaluating=1' : ''}`);
	}
};
