import { needsYouCount } from '$lib/server/db';

export function load() {
	return { needsYou: needsYouCount() };
}
