// Browser setup (core §16g): the choices of `cli.py setup` as a page. Only on the PC itself: it
// writes .env. Secrets go to Python on stdin and never come back; the page only learns "set".
import { error, fail } from '@sveltejs/kit';
import { cli } from '$lib/server/python';

const LOCAL_ONLY = 'Setup is only available on the PC that runs JobHunter.';

export function load({ locals }) {
	if (!locals.local) error(403, LOCAL_ONLY);
	const s = cli(['setup-state']);
	if (s.error) error(500, s.error);
	return { s };
}

export const actions = {
	default: async ({ request, locals }) => {
		if (!locals.local) error(403, LOCAL_ONLY);
		const payload = Object.fromEntries([...(await request.formData())].map(([k, v]) => [k, String(v)]));
		const r = cli(['setup-apply'], null, JSON.stringify(payload));
		// Only the step name and Python's answer go back to the page, never what was typed.
		if (r.error) return fail(400, { step: payload.step, error: String(r.error) });
		return { step: payload.step, ...r };
	}
};
