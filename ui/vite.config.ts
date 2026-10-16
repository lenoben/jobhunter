import { sveltekit } from '@sveltejs/kit/vite';
import { existsSync, readFileSync } from 'node:fs';
import { defineConfig } from 'vite';

// Localhost only, unless UI_LAN=1 in ../.env (hotspot access). Either way src/hooks.server.ts
// decides who gets in: this PC, or paired devices from UI_LAN_SUBNETS.
const envFile = new URL('../.env', import.meta.url);
const lan = existsSync(envFile) && /^\s*UI_LAN\s*=\s*["']?1["']?\s*$/m.test(readFileSync(envFile, 'utf-8'));
const host = lan ? '0.0.0.0' : '127.0.0.1';

export default defineConfig({
	plugins: [sveltekit()],
	server: { host, port: 5173, strictPort: true },
	preview: { host, port: 5173, strictPort: true }
});
