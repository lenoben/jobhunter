import { fail } from '@sveltejs/kit';
import { attentionJobs, decideReview, reviewJobs } from '$lib/server/db';
import { runNow } from '$lib/server/files';

export function load() {
	return { jobs: attentionJobs(), review: reviewJobs() };
}

function ids(f: FormData) {
	return f.getAll('id').map(Number).filter((v) => Number.isInteger(v) && v > 0);
}

export const actions = {
	/** Alert jobs the user picked: evaluate (→ new; evaluate_now also starts "Score waiting jobs") or dismiss. */
	review: async ({ request }) => {
		const f = await request.formData();
		const picked = ids(f);
		if (!picked.length) return fail(400, { error: 'tick at least one job first' });
		const decision = String(f.get('decision') ?? '');
		const to = decision === 'skip' ? 'skipped' : 'new';
		const n = decideReview(picked, to);
		if (to === 'skipped') return { reviewed: `${n} dismissed.` };
		if (decision === 'evaluate_now') return { reviewed: `${n} sent to evaluation. ${runNow('evaluate')}` };
		return { reviewed: `${n} sent to evaluation: the next run scores them, or press "Score waiting jobs" on the Jobs page.` };
	}
};
