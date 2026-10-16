<script lang="ts">
	let { form } = $props();
</script>

<svelte:head><title>Pair this device · JobHunter</title></svelte:head>

<div class="card" style="max-width: 420px; margin: 2rem auto">
	<h1>Pair this device</h1>
	<p class="small muted">On the PC, open <strong>Settings → Pair a device</strong> and enter the 6-digit code here.
		This device then stays signed in for a year.</p>
	{#if form?.error}<div class="flash">{form.error}</div>{/if}
	<form method="POST" class="row">
		<!-- no pattern attribute: Svelte would read "{6}" in it as an expression -->
		<input type="text" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="12"
			placeholder="123456" required class="grow" style="font-size: 1.4rem; letter-spacing: 0.3em; text-align: center" />
		<button>Pair</button>
	</form>
</div>
