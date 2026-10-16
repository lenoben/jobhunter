import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
export default {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter(),
		// Open tabs (e.g. a paired tablet) check for a new build every minute; the next click then
		// loads the page fresh instead of failing with "500 Internal Error" on stale JS files.
		version: { pollInterval: 60_000 }
	}
};
