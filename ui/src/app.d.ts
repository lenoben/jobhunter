declare global {
	namespace App {
		interface Locals {
			/** Request comes from this PC (loopback), not from a paired hotspot device. */
			local: boolean;
			/** Request came through the reverse tunnel (UI_TUNNEL_HOSTS); always a paired device. */
			tunnel: boolean;
		}
	}
}

export {};
