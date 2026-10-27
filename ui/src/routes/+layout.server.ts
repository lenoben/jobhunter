import { needsYouCount, recruiterUnseenCount, reviewCount } from '$lib/server/db';

export function load() {
	return { needsYou: needsYouCount(), review: reviewCount(), recruiters: recruiterUnseenCount() };
}
