import { fail } from '@sveltejs/kit';
import { deleteBoard, listBoards, saveBoard } from '$lib/server/db';

export function load() {
	return { boards: listBoards() };
}

function id(f: FormData) {
	const v = Number(f.get('id'));
	return Number.isInteger(v) && v > 0 ? v : null;
}

export const actions = {
	/** Add (no id) or edit (id) a bookmark. */
	save: async ({ request }) => {
		const f = await request.formData();
		const values = { name: String(f.get('name') ?? ''), url: String(f.get('url') ?? ''), note: String(f.get('note') ?? '').trim() };
		try {
			saveBoard(id(f), values.name, values.url, values.note || null);
		} catch (e) {
			return fail(400, { error: (e as Error).message, values, editing: id(f) });
		}
		return { saved: true };
	},
	delete: async ({ request }) => {
		const b = id(await request.formData());
		if (b === null) return fail(400, { error: 'bad id' });
		deleteBoard(b);
		return { deleted: true };
	}
};
