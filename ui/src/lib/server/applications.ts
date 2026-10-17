// The list of applications as a record of one's own job search ("Nachweis der Eigenbemühungen"
// for the Agentur für Arbeit / Jobcenter): German labels, CSV for Excel, and a printable page.
import { applicationList } from './db';
import { loadProfile } from './profile';

const HOSTS: [RegExp, string][] = [
	[/linkedin\./, 'LinkedIn'], [/indeed\./, 'Indeed'], [/glassdoor\./, 'Glassdoor'], [/stepstone\./, 'StepStone'],
	[/xing\./, 'XING'], [/instaffo\./, 'Instaffo'], [/arbeitsagentur\./, 'Jobbörse der Bundesagentur für Arbeit'],
	[/arbeitnow\./, 'Arbeitnow']
];

function host(url: string | null): string | null {
	try {
		return url ? new URL(url).hostname.replace(/^www\./, '') : null;
	} catch {
		return null;
	}
}

/** Where the job was found ("Fundstelle"). */
export function sourceLabel(source: string, url: string | null): string {
	if (source === 'ba_jobsuche') return 'Jobbörse der Bundesagentur für Arbeit';
	if (source === 'arbeitnow') return 'Arbeitnow';
	const h = host(url) ?? '';
	const board = HOSTS.find(([re]) => re.test(h))?.[1];
	if (source === 'email_alerts') return `${board ?? 'Job'}-Alert (E-Mail)`;
	return board ?? (h ? `Karriereseite (${h})` : 'Sonstige');
}

/** How the user applied ("Art der Bewerbung"). */
export function methodLabel(r: { apply_method: string | null; method: string | null; apply_email: string | null }): string {
	if (r.apply_method === 'email' || /^\s*e-?mail/i.test(r.method ?? '')) {
		return r.apply_email ? `E-Mail (${r.apply_email})` : 'E-Mail';
	}
	return 'Online (Bewerbungsportal)';
}

export const OUTCOME: Record<string, string> = {
	applied: 'offen', interview: 'Vorstellungsgespräch', offer: 'Zusage', rejected: 'Absage', withdrawn: 'zurückgezogen'
};

export function germanDate(utc: string | null): string {
	if (!utc) return '';
	const d = new Date(utc.replace(' ', 'T') + 'Z');
	return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Berlin' });
}

/** Rows with German labels, oldest first (as such records are usually kept). */
export function germanRows(from?: string | null, to?: string | null) {
	return applicationList(from, to).reverse().map((r) => ({
		id: r.id,
		date: germanDate(r.applied_at),
		company: r.company ?? '',
		title: r.title,
		location: r.location ?? '',
		method: methodLabel(r),
		source: sourceLabel(r.source, r.url),
		link: r.apply_url ?? r.url,
		outcome: OUTCOME[r.status] ?? r.status,
		outcomeDate: r.status === 'applied' ? '' : germanDate(r.status_at)
	}));
}

export const COLUMNS: [keyof ReturnType<typeof germanRows>[number], string][] = [
	['date', 'Datum der Bewerbung'], ['company', 'Arbeitgeber'], ['title', 'Stelle'], ['location', 'Arbeitsort'],
	['method', 'Art der Bewerbung'], ['source', 'Fundstelle'], ['link', 'Link zur Stelle'], ['outcome', 'Ergebnis'],
	['outcomeDate', 'Datum des Ergebnisses']
];

/** CSV for German Excel: semicolons, UTF-8 with BOM, CRLF. */
export function applicationsCsv(from?: string | null, to?: string | null): string {
	const cell = (v: unknown) => {
		const s = String(v ?? '');
		return /[";\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
	};
	const lines = [COLUMNS.map(([, h]) => cell(h)).join(';')];
	for (const r of germanRows(from, to)) lines.push(COLUMNS.map(([k]) => cell(r[k])).join(';'));
	return '﻿' + lines.join('\r\n') + '\r\n';
}

export function applicantName(): string {
	return String(loadProfile()?.personal?.name ?? '');
}

/** YYYY-MM-DD or null. */
export function dateParam(v: string | null): string | null {
	return v && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : null;
}
