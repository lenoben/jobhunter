<script lang="ts">
	// Copies `text`. navigator.clipboard only exists in secure contexts (https/localhost); over the
	// hotspot/LAN (plain http) we fall back to a hidden textarea + execCommand('copy').
	let { text, label = 'Copy' }: { text: string; label?: string } = $props();
	let done = $state(false);

	async function copy() {
		try {
			if (navigator.clipboard && window.isSecureContext) {
				await navigator.clipboard.writeText(text);
			} else {
				const ta = document.createElement('textarea');
				ta.value = text;
				ta.setAttribute('readonly', '');
				ta.style.position = 'fixed';
				ta.style.opacity = '0';
				document.body.appendChild(ta);
				ta.select();
				ta.setSelectionRange(0, text.length);
				document.execCommand('copy');
				ta.remove();
			}
			done = true;
			setTimeout(() => (done = false), 1500);
		} catch {
			done = false;
		}
	}
</script>

<button type="button" class="secondary small" onclick={copy} aria-label="{label}: {text.slice(0, 40)}">{done ? '✓ Copied' : label}</button>
