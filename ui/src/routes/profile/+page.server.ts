import { fail } from '@sveltejs/kit';
import { listFilters } from '$lib/server/db';
import { motivations, profilePath, profileText, saveMotivations, saveProfileText } from '$lib/server/profile';

export function load() {
	const filters = listFilters() as any[];
	return {
		motivations: motivations(filters.filter((f) => f.active).map((f) => f.name)),
		text: profileText(),
		path: profilePath()
	};
}

export const actions = {
	/** Motivation per search category (used for cover-letter openings and the apply kit). */
	motivation: async ({ request }) => {
		const f = await request.formData();
		const entries: Record<string, string> = {};
		for (const [k, v] of f.entries()) if (k.startsWith('m:')) entries[k.slice(2)] = String(v);
		const r = saveMotivations(entries);
		if ('error' in r) return fail(400, { error: r.error });
		return { saved: 'motivation', warnings: r.warnings };
	},
	/** The whole file, checked by core/profile.py before it is replaced (previous version backed up). */
	raw: async ({ request }) => {
		const text = String((await request.formData()).get('text') ?? '').replace(/\r\n/g, '\n');
		const r = saveProfileText(text);
		if ('error' in r) return fail(400, { error: r.error, text });
		return { saved: 'raw', warnings: r.warnings };
	}
};
