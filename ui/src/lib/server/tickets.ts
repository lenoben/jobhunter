// Feedback tickets (core §16d): reading the form, and what the page needs from Python.
import type { TicketFields } from './db';
import { cli } from './python';
import { KINDS, type TicketDetails } from '$lib/tickets';

const TITLE_MAX = 200;
const BODY_MAX = 20_000;

export function ticketId(v: FormDataEntryValue | string | null): number | null {
	const n = Number(v);
	return Number.isInteger(n) && n > 0 ? n : null;
}

/** The fields of a ticket form, or the reason they can't be saved. Only a title is needed to save. */
export function parseTicket(f: FormData): { fields: TicketFields; error?: string } {
	const fields: TicketFields = {
		kind: String(f.get('kind') ?? ''),
		title: String(f.get('title') ?? '').replace(/\s+/g, ' ').trim(),
		body: String(f.get('body') ?? '').trim(),
		reply_to: String(f.get('reply_to') ?? '').trim() || null,
		include_details: f.get('include_details') ? 1 : 0
	};
	let error: string | undefined;
	if (!KINDS[fields.kind]) error = 'Pick a type.';
	else if (!fields.title) error = 'Enter a short title.';
	else if (fields.title.length > TITLE_MAX) error = `The title is too long (max. ${TITLE_MAX} characters).`;
	else if (fields.body.length > BODY_MAX) error = `The description is too long (max. ${BODY_MAX} characters).`;
	else if (fields.reply_to && !/^[^\s@]+@[^\s@]+$/.test(fields.reply_to)) error = 'The reply address doesn’t look like an email address.';
	return { fields, error };
}

export type FeedbackInfo = { to: string; details: TicketDetails; drafts_available: boolean };

let cached: { at: number; info: FeedbackInfo } | undefined;

/** Starts Python, so kept for 5 minutes. Call it before reading tickets: it also applies migrations. */
export function feedbackInfo(): FeedbackInfo {
	if (cached && Date.now() - cached.at < 5 * 60_000) return cached.info;
	const r = cli(['feedback-info']);
	if (r.error) throw new Error(r.error);
	cached = { at: Date.now(), info: r };
	return r;
}
