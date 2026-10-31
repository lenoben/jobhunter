import { fail, redirect } from '@sveltejs/kit';
import { createTicket, deleteTicket, listTickets } from '$lib/server/db';
import { feedbackInfo, parseTicket, ticketId } from '$lib/server/tickets';

export function load() {
	const { to } = feedbackInfo();
	return { to, tickets: listTickets() };
}

export const actions = {
	/** "Save for later" stays here; "Continue" (next=send) opens the ticket to send it. */
	save: async ({ request }) => {
		const f = await request.formData();
		const { fields, error } = parseTicket(f);
		if (error) return fail(400, { error, values: fields });
		const id = createTicket(fields);
		if (f.get('next') === 'send') redirect(303, `/feedback/${id}`);
		return { saved: fields.title };
	},
	delete: async ({ request }) => {
		const f = await request.formData();
		const id = ticketId(f.get('id'));
		if (id === null || f.get('confirm') !== 'yes') return fail(400, { error: 'bad request' });
		if (!deleteTicket(id)) return fail(400, { error: 'Only drafts can be deleted.' });
		return { deleted: true };
	}
};
