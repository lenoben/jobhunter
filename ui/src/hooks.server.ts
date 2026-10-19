// Access guard (CLAUDE.md §12). SvelteKit's own CSRF check is skipped in dev mode, so this applies
// in dev and production alike:
//  - this PC (loopback): only Host localhost/127.0.0.1 (blocks DNS-rebinding pages);
//  - hotspot devices (UI_LAN=1, UI_LAN_SUBNETS): need a paired device cookie (see /login);
//  - reverse tunnel (loopback + Host in UI_TUNNEL_HOSTS): the same paired device cookie;
//  - anyone else: 403;
//  - state-changing requests must come from the UI itself (same-origin Origin header).
import type { Handle } from '@sveltejs/kit';
import { COOKIE, inLanSubnet, isLoopback, isTunnelHost, LAN_ENABLED, validDeviceCookie } from '$lib/server/access';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

export const handle: Handle = async ({ event, resolve }) => {
	const ip = event.getClientAddress();
	// cloudflared connects from this PC, so a tunnel request is told apart by its Host header.
	const tunnel = isLoopback(ip) && isTunnelHost(event.url.hostname);
	const local = isLoopback(ip) && !tunnel;

	if (local) {
		if (!LOCAL_HOSTS.has(event.url.hostname)) return new Response('Forbidden host', { status: 403 });
	} else if (tunnel || (LAN_ENABLED && inLanSubnet(ip))) {
		const paired = validDeviceCookie(event.cookies.get(COOKIE));
		if (!paired && event.url.pathname !== '/login') {
			return new Response(null, { status: 303, headers: { location: '/login' } });
		}
	} else {
		return new Response('Forbidden', { status: 403 });
	}
	event.locals.local = local;
	event.locals.tunnel = tunnel;

	if (!['GET', 'HEAD', 'OPTIONS'].includes(event.request.method)) {
		const origin = event.request.headers.get('origin');
		// The tunnel ends TLS at Cloudflare: the browser's origin is https while the dev server sees http.
		const allowed = tunnel ? [event.url.origin, `https://${event.url.host}`] : [event.url.origin];
		if (!origin || !allowed.includes(origin)) {
			return new Response('Cross-site requests are forbidden', { status: 403 });
		}
	}
	return resolve(event);
};
