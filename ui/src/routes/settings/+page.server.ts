import { fail } from '@sveltejs/kit';
import { getSettings, purgePreview, SETTING_INFO, updateSettings } from '$lib/server/db';
import { runNow } from '$lib/server/files';
import { cli } from '$lib/server/python';
import { parseCountries } from '$lib/countries';
import { LAN_ENABLED, lanUrls, newPairingCode, PAIRING_ENABLED } from '$lib/server/access';

function modelList(raw: string | undefined): string[] {
	try {
		const list = JSON.parse(raw || '[]');
		return Array.isArray(list) ? list.map(String) : [];
	} catch {
		return [];
	}
}

export function load({ locals, url }) {
	const settings = getSettings();
	return {
		settings,
		models: modelList(settings.llm_models), // the provider's chat models, best first (cli.py llm-models)
		info: SETTING_INFO,
		local: locals.local,
		purge: purgePreview(),
		lan: { enabled: PAIRING_ENABLED, urls: LAN_ENABLED ? lanUrls(Number(url.port || 5790)) : [] }
	};
}

export const actions = {
	save: async ({ request }) => {
		const f = await request.formData();
		const values: Record<string, string> = {};
		const errors: string[] = [];
		for (const [key, { label, kind, options, optional }] of Object.entries(SETTING_INFO)) {
			if (kind === 'countries') {
				const { keys, unknown } = parseCountries(String(f.get(key) ?? ''));
				if (unknown.length) errors.push(`${label}: unknown ${unknown.join(', ')}`);
				else if (!keys.length) errors.push(`${label}: name at least one country, remote or worldwide`);
				values[key] = JSON.stringify(keys);
				continue;
			}
			if (kind === 'choice') {
				const v = String(f.get(key) ?? '');
				if (!options!.includes(v)) errors.push(`${label}: choose one of ${options!.join(', ')}`);
				values[key] = v;
				continue;
			}
			if (kind === 'json') {
				const raw = String(f.get(key) ?? '').trim();
				try {
					const list = JSON.parse(raw);
					const ok = Array.isArray(list) && list.every((s: any) =>
						['linkedin', 'instaffo', 'stepstone', 'xing'].includes(s?.board) && /^[^@\s]+@[^@\s]+$/.test(s?.from ?? ''));
					if (!ok) throw new Error();
					values[key] = JSON.stringify(list);
				} catch {
					errors.push(`${label}: must be a JSON list like [{"board": "linkedin", "from": "jobalerts-noreply@linkedin.com"}]`);
				}
				continue;
			}
			if (kind === 'bool') {
				values[key] = f.get(key) === 'on' ? '1' : '0';
				continue;
			}
			const raw = String(f.get(key) ?? '').trim().replace(',', '.');
			if (kind === 'text') {
				if (!raw && !optional) errors.push(`${label} must not be empty`);
				values[key] = raw;
				continue;
			}
			const n = Number(raw);
			if (raw === '' || !Number.isFinite(n) || n < 0 || (kind === 'int' && !Number.isInteger(n))) {
				errors.push(`${label}: "${raw}" is not a valid ${kind === 'int' ? 'whole number' : 'number'}`);
			}
			values[key] = kind === 'number' ? String(n) : raw;
		}
		if (errors.length) return fail(400, { errors });
		updateSettings(values);
		return { saved: true };
	},
	run: async () => ({ started: runNow() }),
	/** Ask the AI provider in .env for its current models (user request 2026-11-20: changeable later). */
	models: async () => {
		const r = cli(['llm-models']);
		if (/claude-code/.test(r?.error ?? '')) return fail(400, { errors: ['You use Claude Code: pick its models in the two Claude Code fields above. The list is for another AI provider (Setup → AI).'] });
		if (!r?.models) return fail(400, { errors: [`Couldn't load the model list: ${r?.error ?? 'no answer'}`] });
		return { modelsLoaded: r.models.length };
	},
	/** Only on the PC itself: a one-time code for a hotspot device (never shown to LAN clients). */
	pair: async ({ locals }) => {
		if (!locals.local) return fail(403, { errors: ['Pairing codes can only be created on the PC itself.'] });
		if (!PAIRING_ENABLED) return fail(400, { errors: ['Device access is off (UI_LAN=1 or UI_TUNNEL_HOSTS, plus UI_SESSION_SECRET, in .env).'] });
		return { pairing: newPairingCode() };
	}
};
