import { error, fail, redirect } from '@sveltejs/kit';
import { deleteTicket, getTicket, setTicketStatus, updateTicket, type Ticket } from '$lib/server/db';
import { cli } from '$lib/server/python';
import { feedbackInfo, parseTicket, ticketId } from '$lib/server/tickets';
import { ticketBody, ticketSubject } from '$lib/tickets';

export function load({ params }) {
	const info = feedbackInfo();
	const id = ticketId(params.id);
	const ticket = id === null ? undefined : getTicket(id);
	if (!ticket) error(404, 'No such ticket');
	return { info, ticket };
}

/** Saves the form, so a button never acts on older text than the preview shows. */
async function saveForm(request: Request, rawId: string, needBody: boolean) {
	const { fields, error: problem } = parseTicket(await request.formData());
	const id = ticketId(rawId);
	if (problem) return { failed: fail(400, { error: problem }) };
	if (needBody && !fields.body) return { failed: fail(400, { error: 'Write a description first.' }) };
	if (id === null || !updateTicket(id, fields)) return { failed: fail(400, { error: 'Only drafts can be changed.' }) };
	return { ticket: getTicket(id) as Ticket };
}

function move(rawId: string, from: Ticket['status'], to: Ticket['status']) {
	const id = ticketId(rawId);
	if (id === null || !setTicketStatus(id, from, to)) return fail(400, { error: 'The ticket has a different status now.' });
	return { moved: to };
}

export const actions = {
	save: async ({ request, params }) => {
		const r = await saveForm(request, params.id, false);
		return r.failed ?? { saved: true };
	},
	/** Puts it in the user's mailbox as a draft; the ticket stays a draft until they've sent it. */
	draft: async ({ request, params }) => {
		const r = await saveForm(request, params.id, true);
		if (r.failed) return r.failed;
		const details = r.ticket.include_details ? feedbackInfo().details : null;
		const out = cli(['feedback-draft', '--subject', ticketSubject(r.ticket)], ticketBody(r.ticket, details));
		if (out.error) return fail(400, { error: out.error });
		return { drafted: out.folder as string };
	},
	sent: async ({ request, params }) => {
		const r = await saveForm(request, params.id, true);
		return r.failed ?? move(params.id, 'draft', 'sent');
	},
	unsend: ({ params }) => move(params.id, 'sent', 'draft'),
	resolve: ({ params }) => move(params.id, 'sent', 'resolved'),
	reopen: ({ params }) => move(params.id, 'resolved', 'sent'),
	delete: async ({ request, params }) => {
		const id = ticketId(params.id);
		if (id === null || (await request.formData()).get('confirm') !== 'yes') return fail(400, { error: 'bad request' });
		if (!deleteTicket(id)) return fail(400, { error: 'Only drafts can be deleted.' });
		redirect(303, '/feedback?deleted=1');
	}
};
