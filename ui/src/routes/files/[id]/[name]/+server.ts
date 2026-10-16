// Serves the generated PDFs: only names that classify as a generated document (no paths, no other
// files), only from output/<id>/.
import { error } from '@sveltejs/kit';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { classifyDocument, jobDir } from '$lib/server/files';

export function GET({ params }) {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0 || !classifyDocument(params.name)) error(404, 'Not found');
	const path = join(jobDir(id), params.name);
	if (!existsSync(path)) error(404, 'Not found');
	return new Response(readFileSync(path), {
		headers: {
			'content-type': 'application/pdf',
			// the file keeps its descriptive name when downloaded
			'content-disposition': `inline; filename="${params.name}"`,
			'cache-control': 'no-store'
		}
	});
}
