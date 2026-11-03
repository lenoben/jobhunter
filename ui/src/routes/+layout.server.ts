import { redirect } from '@sveltejs/kit';
import { needsYouCount, recruiterUnseenCount, reviewCount, setupState } from '$lib/server/db';

export function load({ locals, url }) {
	// First start (core §16g): the PC itself is sent to the setup page; nothing works without a database.
	const setup = setupState();
	if (setup !== 'ok' && locals.local && url.pathname !== '/setup' && (setup === 'no-db' || url.pathname === '/')) {
		redirect(303, '/setup');
	}
	if (setup === 'no-db') return { needsYou: 0, review: 0, recruiters: 0 };
	return { needsYou: needsYouCount(), review: reviewCount(), recruiters: recruiterUnseenCount() };
}
