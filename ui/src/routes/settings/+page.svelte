<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();
</script>

<svelte:head><title>Settings · JobHunter</title></svelte:head>

<h1>Settings</h1>

{#if form?.errors}<div class="flash">{#each form.errors as e}<div>{e}</div>{/each}</div>{/if}
{#if form?.saved}<div class="flash">Saved. The next run uses the new values.</div>{/if}
{#if form?.started}<div class="flash">{form.started}</div>{/if}

<div class="card row">
	<div class="grow">
		<strong>Run now</strong>
		<div class="muted small">Starts run.ps1 with trigger "manual" in the background. It is refused if a run is still
			running or the last one finished less than {data.settings.min_hours_between_runs} h ago.</div>
	</div>
	<form method="POST" action="?/run" use:enhance><button>▶ Run now</button></form>
</div>

{#if data.local}
	<div class="card">
		<div class="row">
			<div class="grow">
				<strong>Phones and tablets on the PC hotspot</strong>
				{#if data.lan.enabled}
					<div class="muted small">
						Open {#each data.lan.urls as u, i}{i ? ' or ' : ''}<code>{u}</code>{:else}<em>(hotspot not running: turn on Mobile Hotspot)</em>{/each}
						on the device, then enter a pairing code.
					</div>
				{:else}
					<div class="muted small">Off. Set <code>UI_LAN=1</code> and <code>UI_SESSION_SECRET</code> in .env and restart the UI.</div>
				{/if}
			</div>
			{#if data.lan.enabled}
				<form method="POST" action="?/pair" use:enhance><button class="secondary">Pair a device</button></form>
			{/if}
		</div>
		{#if form?.pairing}
			<p style="font-size: 2rem; letter-spacing: 0.3em; margin: 0.6rem 0 0"><strong>{form.pairing.code}</strong></p>
			<p class="muted small" style="margin: 0">Valid for {form.pairing.expiresInMin} minutes, single use.</p>
		{/if}
	</div>
{/if}

<form method="POST" action="?/save" use:enhance={() => async ({ update }) => update({ reset: false })} class="card" style="display: grid; gap: 0.8rem; max-width: 640px">
	{#each Object.entries(data.info) as [key, { label, kind, options }]}
		{#if kind === 'choice'}
			<div>
				<label for={key}>{label}</label>
				<select id={key} name={key}>
					{#each options ?? [] as o}<option value={o} selected={data.settings[key] === o}>{o}</option>{/each}
				</select>
			</div>
		{:else if kind === 'json'}
			<div>
				<label for={key}>{label}</label>
				<textarea id={key} name={key} rows="5" class="small" style="font-family: ui-monospace, Consolas, monospace"
					>{JSON.stringify(JSON.parse(data.settings[key] || '[]'), null, 2)}</textarea>
			</div>
		{:else if kind === 'bool'}
			<div class="checks"><label><input type="checkbox" name={key} checked={data.settings[key] === '1'} /> {label}</label></div>
		{:else}
			<div>
				<label for={key}>{label}</label>
				<input id={key} name={key} type="text" inputmode={kind === 'text' ? 'text' : 'decimal'} value={data.settings[key] ?? ''} style="width: 100%" />
			</div>
		{/if}
	{/each}
	<p class="muted small" style="margin: 0">Update the Blue Card threshold and year each January.</p>
	<div><button>Save settings</button></div>
</form>
