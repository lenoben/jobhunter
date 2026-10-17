<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();
	const empty = $derived(data.motivations.filter((m: any) => m.filter && !m.text).length);
	const keep = () => async ({ update }: any) => update({ reset: false });
</script>

<svelte:head><title>Profile · JobHunter</title></svelte:head>

<h1>Profile</h1>
<p class="muted small">Everything in your documents comes from this profile (nothing is invented). Every save is
	checked first, and the previous version is kept in <code>profile/backups/</code>.</p>

{#if form?.error}<div class="flash">Not saved: {form.error}</div>{/if}
{#if form?.saved}
	<div class="flash">Saved. Documents written from now on use it.
		{#if form.warnings?.length}<div class="small" style="margin-top: 0.4rem">Check:</div>
			<ul class="small" style="margin: 0.2rem 0 0">{#each form.warnings as w}<li>{w}</li>{/each}</ul>{/if}
	</div>
{/if}

<form method="POST" action="?/motivation" use:enhance={keep} class="card" style="display: grid; gap: 0.9rem">
	<div>
		<h2 style="margin: 0">Motivation per category</h2>
		<p class="muted small" style="margin: 0.3rem 0 0">Your own reasons for each kind of job, in a few sentences (German
			or English). Cover letters open with them and the apply kit uses them for "short motivation". If one is empty,
			the letter opens with profile facts instead and the run notes it.
			{#if empty}<strong>{empty} {empty === 1 ? 'category is' : 'categories are'} empty.</strong>{/if}</p>
	</div>
	{#each data.motivations as m}
		<div>
			<label for="m-{m.name}">{m.name}{#if !m.filter} <span class="muted small">(no active filter with this name)</span>{/if}</label>
			<textarea id="m-{m.name}" name="m:{m.name}" rows="4" style="width: 100%"
				placeholder="Why this kind of work? What draws you to it, what you want to build or learn, and why it fits your path.">{m.text}</textarea>
		</div>
	{/each}
	<div><button>Save motivation</button></div>
</form>

<details class="card" open={form?.saved === 'raw' || (form?.error && form?.text !== undefined)}>
	<summary><strong>Whole profile (YAML)</strong> <span class="muted small">experience, education, skills, projects, availability …</span></summary>
	<form method="POST" action="?/raw" use:enhance={keep} style="display: grid; gap: 0.6rem; margin-top: 0.8rem">
		<p class="muted small" style="margin: 0">Dates as MM/YYYY. Keep the structure; a save that breaks a required
			section is refused. File: <code>{data.path}</code></p>
		<textarea name="text" rows="30" spellcheck="false" style="width: 100%; font-family: ui-monospace, Consolas, monospace; font-size: 0.85rem"
			>{form?.text ?? data.text}</textarea>
		<div><button>Check and save</button></div>
	</form>
</details>
