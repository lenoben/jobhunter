// Who may use the UI (CLAUDE.md §12, LAN extension).
//  - Loopback (this PC): always, no login.
//  - Devices in UI_LAN_SUBNETS (default: the Windows hotspot 192.168.137.0/24), only if UI_LAN=1,
//    and only with a device cookie obtained by entering a one-time pairing code shown on the PC.
//  - Everything else: refused.
// UI_SESSION_SECRET (in .env, R3) signs the device cookies; it is never sent to a browser.
import { createHmac, randomBytes, randomInt, timingSafeEqual } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { networkInterfaces } from 'node:os';
import { join } from 'node:path';
import { ROOT } from './db';

export const COOKIE = 'jh_device';
const PAIR_TTL_MS = 10 * 60 * 1000;
const MAX_FAILS = 5;

/** Reads only the UI_* keys from the project's .env (never the mail/Telegram secrets). */
function readUiEnv(): Record<string, string> {
	const out: Record<string, string> = {};
	const path = join(ROOT, '.env');
	if (!existsSync(path)) return out;
	for (const line of readFileSync(path, 'utf-8').split(/\r?\n/)) {
		const m = line.match(/^\s*(UI_[A-Z_]+)\s*=\s*(.*?)\s*$/);
		if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, '');
	}
	return out;
}

const env = { ...readUiEnv(), ...Object.fromEntries(Object.entries(process.env).filter(([k]) => k.startsWith('UI_'))) };
const SECRET = env.UI_SESSION_SECRET ?? '';
export const LAN_ENABLED = env.UI_LAN === '1' && SECRET.length >= 32;
const SUBNETS = (env.UI_LAN_SUBNETS || '192.168.137.0/24').split(',').map((s) => s.trim()).filter(Boolean);

function ipv4(ip: string): number | null {
	const m = ip.replace(/^::ffff:/i, '').match(/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
	if (!m) return null;
	const parts = m.slice(1).map(Number);
	if (parts.some((p) => p > 255)) return null;
	return ((parts[0] << 24) >>> 0) + (parts[1] << 16) + (parts[2] << 8) + parts[3];
}

export function isLoopback(ip: string): boolean {
	return ip === '::1' || /^(::ffff:)?127\./i.test(ip);
}

export function inLanSubnet(ip: string): boolean {
	const n = ipv4(ip);
	if (n === null) return false;
	return SUBNETS.some((cidr) => {
		const [base, bits] = cidr.split('/');
		const b = ipv4(base);
		const len = Number(bits ?? 32);
		if (b === null || !(len >= 8 && len <= 32)) return false;
		const mask = len === 32 ? 0xffffffff : (~((1 << (32 - len)) - 1)) >>> 0;
		return ((n & mask) >>> 0) === ((b & mask) >>> 0);
	});
}

// ── device cookies ──────────────────────────────────────────────────────────

function sign(id: string): string {
	return createHmac('sha256', SECRET).update(id).digest('base64url');
}

export function newDeviceCookie(): string {
	const id = randomBytes(16).toString('base64url');
	return `${id}.${sign(id)}`;
}

export function validDeviceCookie(value: string | undefined): boolean {
	if (!LAN_ENABLED || !value) return false;
	const [id, mac] = value.split('.');
	if (!id || !mac) return false;
	const expected = Buffer.from(sign(id));
	const given = Buffer.from(mac);
	return given.length === expected.length && timingSafeEqual(given, expected);
}

// ── pairing codes (in memory, single use, shown only on the PC) ─────────────

let pairing: { code: string; expires: number } | null = null;
let fails = { count: 0, since: 0 };

export function newPairingCode(): { code: string; expiresInMin: number } {
	pairing = { code: String(randomInt(0, 1_000_000)).padStart(6, '0'), expires: Date.now() + PAIR_TTL_MS };
	fails = { count: 0, since: Date.now() };
	return { code: pairing.code, expiresInMin: PAIR_TTL_MS / 60000 };
}

/** 'ok' consumes the code. After MAX_FAILS wrong tries the code is burned (new one needed). */
export function checkPairingCode(code: string): 'ok' | 'wrong' | 'expired' | 'locked' {
	if (!pairing || Date.now() > pairing.expires) return 'expired';
	if (fails.count >= MAX_FAILS) return 'locked';
	const a = Buffer.from(code.trim());
	const b = Buffer.from(pairing.code);
	if (a.length === b.length && timingSafeEqual(a, b)) {
		pairing = null;
		return 'ok';
	}
	fails.count++;
	if (fails.count >= MAX_FAILS) pairing = null;
	return 'wrong';
}

/** URLs a device on the hotspot can open (shown on the PC's Settings page). */
export function lanUrls(port: number): string[] {
	const urls: string[] = [];
	for (const addrs of Object.values(networkInterfaces())) {
		for (const a of addrs ?? []) {
			if (a.family === 'IPv4' && !a.internal && inLanSubnet(a.address)) urls.push(`http://${a.address}:${port}/`);
		}
	}
	return urls;
}
