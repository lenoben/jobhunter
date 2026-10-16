declare global {
	namespace App {
		interface Locals {
			/** Request comes from this PC (loopback), not from a paired hotspot device. */
			local: boolean;
		}
	}
}

export {};
