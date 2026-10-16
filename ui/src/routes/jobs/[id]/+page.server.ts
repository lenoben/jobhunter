import { error, fail } from '@sveltejs/kit';
import {
	approveInferred, DOC_CHOICES, flagWorkAuthorization, getApplication, getHistory, getJob, getSettings, markApplied, notInterested,
	rejectInferred, requestDocuments, setStatus, USER_SETTABLE
} from '$lib/server/db';
import { listDocuments, markdown, notesHtml, runNow } from '$lib/server/files';
import { buildKit } from '$lib/server/kit';
import { cli } from '$lib/server/python';

function jobId(params: { id: string }) {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) error(404, 'Not found');
	return id;
}

export function load({ params, url }) {
	const id = jobId(params);
	const job = getJob(id);
	if (!job) error(404, 'Job not found');
	return {
		job,
		application: getApplication(id),
		history: getHistory(id),
		documents: listDocuments(id),
		notes: notesHtml(id),
		fitNotes: markdown(job.fit_notes),
		statuses: USER_SETTABLE,
		docChoices: DOC_CHOICES,
		kit: buildKit(job),
		added: url.searchParams.get('added'),
		evaluating: url.searchParams.get('evaluating') === '1',
		docThreshold: Number(getSettings().min_fit_for_documents ?? 60)
	};
}

async function form(request: Request) {
	const f = await request.formData();
	return { note: String(f.get('note') ?? '').trim() || null, status: String(f.get('status') ?? '') };
}

function run(fn: () => void) {
	try {
		fn();
		return { ok: true };
	} catch (e) {
		return fail(400, { error: (e as Error).message });
	}
}

export const actions = {
	status: async ({ params, request }) => {
		const { status, note } = await form(request);
		return run(() => setStatus(jobId(params), status, note));
	},
	applied: async ({ params, request }) => {
		const { note } = await form(request);
		return run(() => markApplied(jobId(params), note));
	},
	skip: async ({ params, request }) => {
		const { note } = await form(request);
		return run(() => notInterested(jobId(params), note));
	},
	/** "Apply anyway" / "Write documents" (CV, cover letter or both). now=1 → "Generate now". */
	docs: async ({ params, request }) => {
		const f = await request.formData();
		const result = run(() => requestDocuments(jobId(params), String(f.get('which') ?? 'both')));
		if ('status' in result) return result; // failure
		return f.get('now') === '1' ? { ok: true, started: runNow('docs') } : { ok: true, requested: true };
	},
	/** Add/replace the full posting (e.g. for email-alert jobs); now=1 → evaluate this job now. */
	posting: async ({ params, request }) => {
		const f = await request.formData();
		const id = jobId(params);
		const r = cli(['update-posting', String(id)], String(f.get('text') ?? ''));
		if (r.error) return fail(400, { error: r.error });
		if (f.get('now') === '1' && r.status === 'new') return { ok: true, fromPosting: true, started: runNow('single', id) };
		return { ok: true, postingSaved: r.status };
	},
	workauth: async ({ params, request }) => {
		const { note } = await form(request);
		return run(() => flagWorkAuthorization(jobId(params), note));
	},
	approve: async ({ params }) => run(() => approveInferred(jobId(params))),
	reject: async ({ params, request }) => {
		const { note } = await form(request);
		return run(() => rejectInferred(jobId(params), note));
	}
};
