import { fail } from '@sveltejs/kit';
import { deleteFilter, listFilters, toggleFilter } from '$lib/server/db';

export function load() {
	return { filters: listFilters() };
}

async function id(request: Request) {
	const v = Number((await request.formData()).get('id'));
	return Number.isInteger(v) && v > 0 ? v : null;
}

export const actions = {
	toggle: async ({ request }) => {
		const f = await id(request);
		if (f === null) return fail(400, { error: 'bad id' });
		toggleFilter(f);
	},
	delete: async ({ request }) => {
		const f = await id(request);
		if (f === null) return fail(400, { error: 'bad id' });
		deleteFilter(f);
	}
};
