import { applicantName, COLUMNS, dateParam, germanRows } from '$lib/server/applications';

export function load({ url }) {
	const from = dateParam(url.searchParams.get('from'));
	const to = dateParam(url.searchParams.get('to'));
	const de = (d: string | null) => (d ? d.split('-').reverse().join('.') : null);
	const rows = germanRows(from, to);
	return {
		rows,
		columns: COLUMNS.filter(([k]) => k !== 'link'),
		name: applicantName(),
		period: from || to ? `${de(from) ?? rows[0]?.date ?? ''} – ${de(to) ?? rows.at(-1)?.date ?? ''}`
			: rows.length ? `${rows[0].date} – ${rows.at(-1)!.date}` : '',
		created: new Date().toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Berlin' })
	};
}
