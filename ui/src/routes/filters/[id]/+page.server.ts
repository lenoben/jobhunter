import { error, fail, redirect } from '@sveltejs/kit';
import {
	EMPLOYMENT_TYPES, getFilter, LANGUAGES, saveFilter, SOURCES, WORK_MODES, type FilterInput
} from '$lib/server/db';

const DEFAULTS = {
	id: null, name: '', active: true, keywords: [], exclude_keywords: ['Freelance', 'Freiberuflich', 'Selbstständig', 'Senior Principal'],
	location: null, radius_km: 50, work_modes: ['remote', 'hybrid', 'onsite'], employment_types: ['full_time'],
	exclude_freelance: true, languages: ['de', 'en'], sources: [...SOURCES], max_age_days: 7, min_fit_score: 60
};

function parseId(param: string): number | null {
	if (param === 'new') return null;
	const id = Number(param);
	if (!Number.isInteger(id) || id <= 0) error(404, 'Not found');
	return id;
}

export function load({ params }) {
	const id = parseId(params.id);
	const filter = id === null ? DEFAULTS : getFilter(id);
	if (!filter) error(404, 'Filter not found');
	return { filter, options: { WORK_MODES, EMPLOYMENT_TYPES, LANGUAGES, SOURCES } };
}

const list = (v: FormDataEntryValue | null) =>
	String(v ?? '').split(/[,\n]/).map((s) => s.trim()).filter(Boolean);

function int(f: FormData, key: string, min: number, max: number, errors: string[]): number {
	const n = Number(f.get(key));
	if (!Number.isInteger(n) || n < min || n > max) errors.push(`${key} must be a whole number from ${min} to ${max}`);
	return n;
}

export const actions = {
	save: async ({ params, request }) => {
		const id = parseId(params.id);
		const f = await request.formData();
		const errors: string[] = [];
		const pick = (key: string, allowed: string[]) => f.getAll(key).map(String).filter((v) => allowed.includes(v));
		const input: FilterInput = {
			name: String(f.get('name') ?? '').trim(),
			active: f.get('active') === 'on',
			keywords: list(f.get('keywords')),
			exclude_keywords: list(f.get('exclude_keywords')),
			location: String(f.get('location') ?? '').trim() || null,
			radius_km: int(f, 'radius_km', 0, 500, errors),
			work_modes: pick('work_modes', WORK_MODES),
			employment_types: pick('employment_types', EMPLOYMENT_TYPES),
			exclude_freelance: f.get('exclude_freelance') === 'on',
			languages: pick('languages', LANGUAGES),
			sources: pick('sources', SOURCES),
			max_age_days: int(f, 'max_age_days', 1, 100, errors),
			min_fit_score: int(f, 'min_fit_score', 0, 100, errors)
		};
		if (!input.name) errors.push('Name is required');
		if (!input.keywords.length) errors.push('At least one keyword is required');
		for (const k of ['work_modes', 'employment_types', 'languages', 'sources'] as const) {
			if (!input[k].length) errors.push(`Choose at least one of ${k.replace('_', ' ')}`);
		}
		if (errors.length) return fail(400, { errors, filter: { ...input, id } });
		saveFilter(id, input);
		redirect(303, '/filters');
	}
};
