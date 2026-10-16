import { attentionJobs } from '$lib/server/db';

export function load() {
	return { jobs: attentionJobs() };
}
