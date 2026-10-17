import { applicationList, getSettings } from '$lib/server/db';
import { dateParam, methodLabel, OUTCOME, sourceLabel } from '$lib/server/applications';

export function load({ url }) {
	const from = dateParam(url.searchParams.get('from'));
	const to = dateParam(url.searchParams.get('to'));
	const s = getSettings();
	const after = Math.trunc(Number(s.followup_after_days ?? 14)) || 0;
	const silent = Math.trunc(Number(s.followup_no_response_days ?? 42)) || 0;
	const rows = applicationList(from, to).map((r) => ({
		...r,
		methodLabel: methodLabel(r),
		sourceLabel: sourceLabel(r.source, r.url),
		outcome: OUTCOME[r.status],
		followup: r.status !== 'applied' ? null
			: silent && r.days >= silent ? 'no_reply'
			: after && r.days >= after && !r.followed_up_at ? 'due'
			: r.followed_up_at ? 'done' : null
	}));
	const query = new URLSearchParams();
	if (from) query.set('from', from);
	if (to) query.set('to', to);
	return { rows, from, to, query: query.toString(), after, silent };
}
