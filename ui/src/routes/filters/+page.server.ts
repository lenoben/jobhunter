import { fail } from '@sveltejs/kit';
import { deleteFilter, getSettings, listFilters, toggleFilter } from '$lib/server/db';
import { countryLabel, parseCountryList } from '$lib/countries';

export function load() {
	const fallback = parseCountryList(getSettings().search_countries);
	return {
		filters: listFilters().map((f) => ({
			...f,
			where: (f.countries.length ? f.countries : fallback.length ? fallback : ['germany']).map(countryLabel).join(', ')
		}))
	};
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
