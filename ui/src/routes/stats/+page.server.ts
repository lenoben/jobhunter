import { stats, statusCounts } from '$lib/server/db';

export function load({ url }) {
	const period = url.searchParams.get('period') === 'month' ? 'month' : 'day';
	return { ...stats(period), counts: statusCounts() };
}
