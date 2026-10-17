// Opens a saved job board: remembers when, then redirects to its link (only links the user saved).
import { error, redirect } from '@sveltejs/kit';
import { openBoard } from '$lib/server/db';

export function GET({ params }) {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) error(404, 'Not found');
	const url = openBoard(id);
	if (!url) error(404, 'Board not found');
	redirect(303, url);
}
