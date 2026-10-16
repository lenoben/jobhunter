// Apply kit (CLAUDE.md §13) for the job page. Mirrors core/apply_kit.py (same fields, same prompt)
// so the UI doesn't need to start Python. For filling forms only — the user always submits (R1/R2).
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parse } from 'yaml';
import { getDb, ROOT } from './db';
import { jobDir, listDocuments } from './files';

export const PROMPT_INTRO =
	'Fill in this application form using the data below. Upload the CV and cover letter if the ' +
	'form allows it. Do not click the final submit button — stop and tell me when it is ready.\n' +
	'Leave any work-authorization, visa or sponsorship questions empty and point them out to me.\n' +
	'Do not log in, create an account or solve a CAPTCHA — stop and tell me instead.\n' +
	'If the page demands unrestricted work authorization, EU citizenship, or says no visa ' +
	'sponsorship, stop and tell me the exact wording.';

function loadProfile(): any {
	const path = process.env.JOBHUNTER_PROFILE ?? join(ROOT, 'profile', 'profile.yaml');
	return existsSync(path) ? parse(readFileSync(path, 'utf-8')) ?? {} : {};
}

const squash = (s: unknown) => String(s ?? '').replace(/\s+/g, ' ').trim();

export function buildKit(job: any) {
	const profile = loadProfile();
	const p = profile.personal ?? {};
	const addr = p.address ?? {};
	const av = profile.availability ?? {};
	const lang = job.language ?? 'de';
	const name = squash(p.name);
	const cut = name.lastIndexOf(' ');
	const first = cut > 0 ? name.slice(0, cut) : name;
	const last = cut > 0 ? name.slice(cut + 1) : '';

	const documents = listDocuments(job.id);

	const filterName = (getDb().prepare('SELECT name FROM search_filters WHERE id = ?').get(job.filter_id) as any)?.name;
	const fields: [string, unknown][] = [
		['Name', name],
		['First name / Vorname', first],
		['Last name / Nachname', last],
		['Email', p.email],
		['Phone / Telefon', p.phone],
		['Street / Straße', addr.street],
		['Postcode / PLZ', addr.postal_code],
		['City / Ort', addr.city],
		['Country / Land', addr.country],
		['Address (one line)', [addr.street, squash(`${addr.postal_code ?? ''} ${addr.city ?? ''}`), addr.country].filter(Boolean).join(', ')],
		['Earliest start / Eintrittstermin', av.start_date],
		['Hours per week / Wochenstunden', av.hours_per_week],
		['Salary expectation / Gehaltsvorstellung', profile.preferences?.salary_text],
		['LinkedIn', p.linkedin],
		['GitHub', p.github],
		['Website', p.website],
		['Motivation (short)', motivation(job, profile, lang, filterName)]
	];
	const kitFields = fields
		.filter(([, v]) => v !== undefined && v !== null && squash(v) !== '')
		.map(([label, v]) => ({ label, value: squash(v) }));

	const dataBlock = kitFields.map((f) => `- ${f.label}: ${f.value}`).join('\n');
	const docsBlock = documents.map((d) => `- ${d.label}: ${d.path}`).join('\n') || '- (no documents yet)';
	const prompt =
		`${PROMPT_INTRO}\n\nJob: ${job.title} — ${job.company ?? ''}\nApplication page: ${job.url}\n\n` +
		`Data:\n${dataBlock}\n\nFiles to upload:\n${docsBlock}`;
	return { url: job.url, applyMethod: job.apply_method, applyEmail: job.apply_email, documents, fields: kitFields, prompt };
}

/** Opening of this job's letter, else the user's motivation for the category, else the summary. */
function motivation(job: any, profile: any, lang: string, filterName?: string): string | undefined {
	const content = join(jobDir(job.id), 'content.json');
	if (existsSync(content)) {
		const body = JSON.parse(readFileSync(content, 'utf-8'))?.letter?.body;
		if (body?.length) return body[0];
	}
	const own = filterName ? profile.motivation?.[filterName] : undefined;
	if (own && squash(own)) return own;
	return profile[`summary_${lang}`] ?? profile.summary_en;
}
