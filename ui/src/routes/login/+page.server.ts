import { fail, redirect } from '@sveltejs/kit';
import { checkPairingCode, COOKIE, newDeviceCookie } from '$lib/server/access';

export function load({ locals }) {
	if (locals.local) redirect(303, '/'); // this PC never needs to pair
	return {};
}

const MESSAGES = {
	wrong: 'Wrong code.',
	expired: 'No valid code. Create a new one on the PC: Settings → Pair a device.',
	locked: 'Too many wrong tries. Create a new code on the PC.'
};

export const actions = {
	default: async ({ request, cookies, locals, url }) => {
		if (locals.local) redirect(303, '/');
		// Tolerate spaces/dashes and full-width digits from tablet keyboards.
		const code = String((await request.formData()).get('code') ?? '')
			.normalize('NFKC')
			.replace(/\D/g, '');
		const result = checkPairingCode(code);
		if (result !== 'ok') return fail(400, { error: MESSAGES[result] });
		cookies.set(COOKIE, newDeviceCookie(), {
			path: '/',
			httpOnly: true,
			sameSite: 'strict',
			secure: locals.tunnel || url.protocol === 'https:', // plain HTTP inside the hotspot; https via the tunnel
			maxAge: 60 * 60 * 24 * 365
		});
		redirect(303, '/');
	}
};
