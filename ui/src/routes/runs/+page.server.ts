import { listRuns } from '$lib/server/db';

export function load() {
	return { runs: listRuns() };
}
