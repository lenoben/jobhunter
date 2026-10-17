import { error, fail } from '@sveltejs/kit';
import {
	approveInferred, DOC_CHOICES, flagWorkAuthorization, followupState, getApplication, getHistory, getJob, getSettings, markApplied, notInterested,
	rejectInferred, requestDocuments, setStatus, toggleFavorite, USER_SETTABLE
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
		followup: followupState(id),
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
	favorite: async ({ params }) => run(() => toggleFavorite(jobId(params))),
	/** Score the job again from the posting text it has (cli reevaluate), then the single-job run. */
	reevaluate: async ({ params }) => {
		const id = jobId(params);
		const r = cli(['reevaluate', String(id)]);
		if (r.error) return fail(400, { error: r.error });
		runNow('single', id);
		return {
			ok: true,
			reevaluating: r.status === 'needs_attention'
				? `The screening flagged this job again (${r.note}); it waits under "Needs you" instead.`
				: 'Scoring this job now. Reload in 1–3 minutes to see the new fit score; Telegram tells you when it\'s done.'
		};
	},
	/** Where to apply: a link (ATS form) or an email address; empty clears the link. */
	applyto: async ({ params, request }) => {
		const f = await request.formData();
		const r = cli(['apply-to', String(jobId(params)), String(f.get('target') ?? '').trim()]);
		if (r.error) return fail(400, { error: r.error });
		return {
			ok: true,
			applySaved: r.apply_email ? `Saved: apply by email to ${r.apply_email} (an email draft is prepared with the documents).`
				: r.apply_url ? 'Saved: the apply kit opens this link.' : 'Link removed; the apply kit uses the posting link.'
		};
	},
	/** A ready follow-up message for an application without a reply (core/followups.py). */
	followuptext: async ({ params }) => {
		const r = cli(['followup-text', String(jobId(params))]);
		if (r.error) return fail(400, { error: r.error });
		return { ok: true, followupText: r as { subject: string; body: string; language: string } };
	},
	followedup: async ({ params }) => {
		const r = cli(['followed-up', String(jobId(params))]);
		if (r.error) return fail(400, { error: r.error });
		return { ok: true, followedUp: true };
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
