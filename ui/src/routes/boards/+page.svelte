<script lang="ts">
	import { enhance } from '$app/forms';
	import { localTime } from '$lib/format';

	let { data, form } = $props();
	let editing = $state<number | null>(null);

	// German boards the scheduled runs don't search; one click saves them.
	const SUGGESTIONS = [
		{ name: 'StepStone', url: 'https://www.stepstone.de/jobs/softwareentwickler' },
		{ name: 'XING Jobs', url: 'https://www.xing.com/jobs/search?keywords=Softwareentwickler' },
		{ name: 'Get in IT', url: 'https://www.get-in-it.de/jobsuche' },
		{ name: 'GermanTechJobs', url: 'https://germantechjobs.de/' },
		{ name: 'Berlin Startup Jobs', url: 'https://berlinstartupjobs.com/engineering/' },
		{ name: 'Jobware', url: 'https://www.jobware.de/' },
		{ name: 'Wellfound (startups)', url: 'https://wellfound.com/location/germany' },
		{ name: 'Make it in Germany', url: 'https://www.make-it-in-germany.com/en/working-in-germany/job-listings' }
	];
	const suggestions = $derived(SUGGESTIONS.filter((s) => !data.boards.some((b: any) => b.url === s.url)));
</script>

<svelte:head><title>Job boards · JobHunter</title></svelte:head>

<h1>Job boards <span class="muted small">{data.boards.length} saved</span></h1>
<p class="muted small">Boards and saved searches the scheduled runs don't cover. Open one, find a job, then copy its link
	and posting into <a href="/?add=1">+ Add a job</a>. These links are only opened by you, never fetched by JobHunter.</p>

{#if form?.error}<div class="flash">{form.error}</div>{/if}

<form class="card" method="POST" action="?/save" use:enhance style="display: grid; gap: 0.6rem">
	<strong>+ Save a job board</strong>
	<div class="row">
		<input type="text" name="name" required placeholder="Name, e.g. StepStone – Python Mannheim" class="grow"
			value={form?.editing ? '' : (form?.values?.name ?? '')} />
		<input type="url" name="url" required placeholder="https://… (a board or a saved search)" class="grow"
			value={form?.editing ? '' : (form?.values?.url ?? '')} />
	</div>
	<div class="row">
		<input type="text" name="note" placeholder="Note (optional), e.g. filter: remote, last 7 days" class="grow" />
		<button>Save</button>
	</div>
</form>

<div class="table-wrap">
	<table>
		<thead><tr><th>Board</th><th class="hide-sm">Note</th><th class="hide-sm">Last opened</th><th></th></tr></thead>
		<tbody>
			{#each data.boards as b (b.id)}
				{#if editing === b.id}
					<tr>
						<td colspan="4">
							<form method="POST" action="?/save" class="row"
								use:enhance={() => async ({ update, result }) => { await update(); if (result.type === 'success') editing = null; }}>
								<input type="hidden" name="id" value={b.id} />
								<input type="text" name="name" required value={b.name} class="grow" aria-label="Name" />
								<input type="url" name="url" required value={b.url} class="grow" aria-label="Link" />
								<input type="text" name="note" value={b.note ?? ''} placeholder="Note" class="grow" aria-label="Note" />
								<button>Save</button>
								<button type="button" class="ghost" onclick={() => (editing = null)}>Cancel</button>
							</form>
						</td>
					</tr>
				{:else}
					<tr>
						<td>
							<a href="/boards/{b.id}/open" target="_blank" rel="noopener noreferrer"><strong>{b.name}</strong> ↗</a>
							<div class="muted small url">{b.url}</div>
						</td>
						<td class="hide-sm small">{b.note ?? ''}</td>
						<td class="hide-sm muted small">{b.last_opened_at ? localTime(b.last_opened_at) : 'never'}</td>
						<td>
							<div class="row" style="gap: 0.3rem; flex-wrap: nowrap">
								<button class="secondary small" onclick={() => (editing = b.id)}>Edit</button>
								<form method="POST" action="?/delete" use:enhance>
									<input type="hidden" name="id" value={b.id} />
									<button class="ghost small" title="Delete this bookmark">✕</button>
								</form>
							</div>
						</td>
					</tr>
				{/if}
			{:else}
				<tr><td colspan="4" class="muted">No boards saved yet. Add one above, or pick a suggestion below.</td></tr>
			{/each}
		</tbody>
	</table>
</div>

{#if suggestions.length}
	<div class="card" style="margin-top: 1rem">
		<strong>Suggestions</strong> <span class="muted small">German boards the scheduled runs don't search. Adjust the search on the board, then edit the saved link.</span>
		<div class="row" style="margin-top: 0.6rem">
			{#each suggestions as s}
				<form method="POST" action="?/save" use:enhance>
					<input type="hidden" name="name" value={s.name} />
					<input type="hidden" name="url" value={s.url} />
					<button class="secondary small" title={s.url}>+ {s.name}</button>
				</form>
			{/each}
		</div>
	</div>
{/if}

<style>
	.url { word-break: break-all; }
</style>
