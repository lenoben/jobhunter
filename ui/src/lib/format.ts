// Shared display helpers (client + server).

/** SQLite datetime('now') is UTC without a zone marker. */
export function localTime(utc: string | null | undefined): string {
	if (!utc) return '–';
	const d = new Date(utc.replace(' ', 'T') + 'Z');
	if (isNaN(d.getTime())) return utc;
	return d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
}

export function label(s: string | null | undefined): string {
	return (s ?? '').replace(/_/g, ' ');
}

export const ATTENTION_HELP: Record<string, string> = {
	needs_login: 'The application portal needs an account or login. Log in yourself and apply.',
	captcha: 'A CAPTCHA blocked the form. Open it and solve it yourself.',
	form_unclear: 'The application form was unclear. Check it and fill it in yourself.',
	missing_profile_info: 'The posting needs something your profile does not show. Add it to profile.yaml if true, then set the job back to shortlisted.',
	german_only_form: 'The form is German-only. Check the answers yourself.',
	source_error: 'The job board failed for this posting. Open the link and check it.',
	work_authorization: 'The ad demands a specific work authorization. Read it and decide yourself.',
	below_blue_card_threshold: 'The stated salary is below the EU Blue Card threshold. Decide whether it is worth it.',
	inferred_facts: 'The documents contain statements implied by, but not written in, your profile. Approve or reject them.'
};
