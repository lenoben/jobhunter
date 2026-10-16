// Production launcher: `npm run build` once, then `npm start`.
// Binds to 127.0.0.1:5173, or to all interfaces when UI_LAN=1 in ../.env (hotspot access;
// src/hooks.server.ts then only lets in paired devices from UI_LAN_SUBNETS).
import { existsSync, readFileSync } from 'node:fs';
import { createServer } from 'node:http';

const envFile = new URL('../.env', import.meta.url);
const lan = existsSync(envFile) && /^\s*UI_LAN\s*=\s*["']?1["']?\s*$/m.test(readFileSync(envFile, 'utf-8'));
const host = process.env.HOST ?? (lan ? '0.0.0.0' : '127.0.0.1');
const port = Number(process.env.PORT ?? 5173);

// adapter-node assumes https unless a protocol header says otherwise, which breaks the same-origin
// check for this plain-HTTP server. We set our own header on every request (clients can't spoof it,
// it is overwritten) and tell the handler to read it. Must be set before the handler is imported.
process.env.PROTOCOL_HEADER = 'x-jobhunter-proto';
const { handler } = await import('./build/handler.js');

createServer((req, res) => {
	req.headers['x-jobhunter-proto'] = 'http';
	handler(req, res);
}).listen(port, host, () => {
	console.log(`JobHunter UI on http://localhost:${port}/` + (lan ? ' (hotspot devices: see Settings)' : ' (this PC only)'));
});
