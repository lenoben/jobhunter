// The text of a feedback ticket (core §16d). Used by the page's live preview and by the server for
// the mailbox draft, so what the user sees is exactly what goes out.
export const KINDS: Record<string, { label: string; emoji: string }> = {
	issue: { label: 'Issue', emoji: '🐞' },
	improvement: { label: 'Improvement', emoji: '💡' },
	suggestion: { label: 'Suggestion', emoji: '💬' }
};

export const TICKET_STATUS: Record<string, string> = { draft: 'Draft', sent: 'Sent', resolved: 'Resolved' };

export type TicketDetails = { os: string; llm_provider: string; commit: string };

type TicketText = { ref: string; kind: string; title: string; body: string; reply_to?: string | null };

export function ticketSubject(t: TicketText): string {
	return `[JobHunter ${KINDS[t.kind]?.label ?? 'Ticket'} ${t.ref}] ${t.title.trim()}`;
}

/** details: null when the user left the technical-details box unticked. */
export function ticketBody(t: TicketText, details: TicketDetails | null): string {
	const footer = [`Ticket: ${t.ref}`];
	if (t.reply_to?.trim()) footer.push(`Reply to: ${t.reply_to.trim()}`);
	if (details) footer.push(`OS: ${details.os}`, `LLM provider: ${details.llm_provider}`, `Version: ${details.commit}`);
	return `${t.body.trim()}\n\n---\n${footer.join('\n')}\n`;
}

// Windows and some mail apps cut off long mailto: links without saying so.
const MAILTO_MAX = 1900;

/** The mailto: link, or null when it would be too long to arrive whole. */
export function ticketMailto(to: string, subject: string, body: string): string | null {
	const q = (s: string) => encodeURIComponent(s.replace(/\r?\n/g, '\r\n'));
	const href = `mailto:${to}?subject=${q(subject)}&body=${q(body)}`;
	return href.length <= MAILTO_MAX ? href : null;
}
