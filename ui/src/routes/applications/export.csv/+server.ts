import { applicationsCsv, dateParam } from '$lib/server/applications';

export function GET({ url }) {
	const from = dateParam(url.searchParams.get('from'));
	const to = dateParam(url.searchParams.get('to'));
	const name = `Bewerbungen${from ? '_ab_' + from : ''}${to ? '_bis_' + to : ''}.csv`;
	return new Response(applicationsCsv(from, to), {
		headers: {
			'Content-Type': 'text/csv; charset=utf-8',
			'Content-Disposition': `attachment; filename="${name}"`,
			'Cache-Control': 'no-store'
		}
	});
}
