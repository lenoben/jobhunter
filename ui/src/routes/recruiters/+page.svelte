<script lang="ts">
	import { enhance } from '$app/forms';
	import { label, localTime } from '$lib/format';
	import ConfirmDelete from '$lib/ConfirmDelete.svelte';

	let { data, form } = $props();
	let editing = $state<number | null>(null);
	let busy = $state(false);

	const submitting = () => {
		busy = true;
		return async ({ update }: { update: (o?: { reset?: boolean }) => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
</script>

<svelte:head><title>Recruiters · JobHunter</title></svelte:head>

<h1>Recruiters <span class="muted small">{data.recruiters.length} on your list</span></h1>
<p class="muted small intro">Recruiting and staffing agencies post jobs for their clients. Runs still find and score those
	jobs, but they <strong>never write documents for them on their own</strong>: such a job gets a <span class="tag recruiter">🤝 Recruiter</span>
	badge, and you decide on the job page whether to apply. Companies on this list are tagged as soon as a job of theirs is
	found; the scoring model also tags postings written “on behalf of a client”.</p>

{#if form?.error}<div class="flash">{form.error}</div>{/if}
{#if form?.added}
	<div class="flash">
		<strong>{form.added.name}</strong> added.
		{#if form.added.tagged.length}{form.added.tagged.length} job{form.added.tagged.length === 1 ? '' : 's'} you already had {form.added.tagged.length === 1 ? 'is' : 'are'} tagged now:
			<ul class="tagged">
				{#each form.added.tagged.slice(0, 12) as j}
					<li><a href="/jobs/{j.id}">{j.title}</a> <span class="muted">— {j.company} · {label(j.status)}</span></li>
				{/each}
			</ul>
			{#if form.added.tagged.length > 12}<a href="/?recruiter=1">… all {form.added.tagged.length}</a>{/if}
		{:else}No job you already had matches; new ones are tagged when they're found.{/if}
	</div>
{/if}
{#if form?.updated}<div class="flash">{form.updated.name} saved · {form.updated.tagged} job(s) tagged.</div>{/if}
{#if form?.removed !== undefined}<div class="flash">Removed from the list; {form.removed} job(s) lost the badge.</div>{/if}
{#if form?.cleared}<div class="flash">Marked as not a recruiter.</div>{/if}

<form class="card add" method="POST" action="?/add" use:enhance={submitting}>
	<strong>+ Add a recruiter</strong>
	<div class="row">
		<input type="text" name="names" required class="grow" value={form?.values?.names ?? ''}
			placeholder="Name, plus other spellings separated by commas, e.g. Hays, Hays AG, Hays Talent Solutions" aria-label="Names" />
	</div>
	<div class="row">
		<input type="text" name="note" class="grow" value={form?.values?.note ?? ''} placeholder="Note (optional), e.g. called me about a Siemens role" aria-label="Note" />
		<button disabled={busy}>{busy ? 'Searching your jobs …' : 'Add & tag jobs'}</button>
	</div>
	<p class="muted small" style="margin: 0">Matched against the company name only, ignoring case and legal forms (GmbH, AG …).
		“Hays” also matches “Hays Professional Solutions”, but not “Haystack”.</p>
</form>

{#if data.recruiters.length}
	<div class="table-wrap">
		<table class="stack">
			<thead><tr><th>Recruiter</th><th class="hide-sm">Note</th><th>Jobs</th><th class="hide-sm">Added</th><th></th></tr></thead>
			<tbody>
				{#each data.recruiters as r (r.id)}
					{#if editing === r.id}
						<tr>
							<td colspan="5">
								<form method="POST" action="?/update" class="row"
									use:enhance={() => async ({ update, result }) => { await update(); if (result.type === 'success') editing = null; }}>
									<input type="hidden" name="id" value={r.id} />
									<input type="text" name="names" required value={r.names.join(', ')} class="grow" aria-label="Names" />
									<input type="text" name="note" value={r.note ?? ''} placeholder="Note" class="grow" aria-label="Note" />
									<button>Save</button>
									<button type="button" class="ghost" onclick={() => (editing = null)}>Cancel</button>
								</form>
							</td>
						</tr>
					{:else}
						<tr>
							<td class="fill">
								<strong>{r.names[0]}</strong>
								{#if r.names.length > 1}<div class="muted small">also: {r.names.slice(1).join(', ')}</div>{/if}
							</td>
							<td class="hide-sm small">{r.note ?? ''}</td>
							<td data-label="Jobs">{#if r.jobs}<a href="/?recruiter_id={r.id}&status=all">{r.jobs}</a>{:else}<span class="muted">0</span>{/if}</td>
							<td class="hide-sm muted small">{localTime(r.created_at)}</td>
							<td>
								<div class="row" style="gap: 0.3rem; flex-wrap: nowrap">
									<button class="secondary small" onclick={() => (editing = r.id)}>Edit</button>
									<ConfirmDelete action="?/remove" id={r.id} small label="Remove" title="Remove from the list"
										question={`Remove ${r.names[0]}? ${r.jobs} job(s) lose the badge.`} />
								</div>
							</td>
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>
	</div>
{:else}
	<p class="muted">No recruiters yet. Add the agencies you know, e.g. ones that contacted you.</p>
{/if}

{#if data.detected.length}
	<h2>Found by the scoring model <span class="muted small">{data.detected.length}</span></h2>
	<p class="muted small">Postings the model read as written by an agency or for a client. Add the agency to your list, or
		clear the badge if it's the employer itself.</p>
	<div class="table-wrap">
		<table class="stack">
			<thead><tr><th>Job</th><th>Why</th><th class="hide-sm">Fit</th><th class="hide-sm">Status</th><th></th></tr></thead>
			<tbody>
				{#each data.detected as j (j.id)}
					<tr>
						<td class="fill"><a href="/jobs/{j.id}"><strong>{j.title}</strong></a>
							<div class="muted small">{j.company ?? '–'}{j.location ? ` · ${j.location}` : ''}</div></td>
						<td class="small full">{j.recruiter_reason ?? ''}</td>
						<td class="hide-sm score">{j.fit_score ?? ''}</td>
						<td class="hide-sm"><span class="pill s-{j.status}">{label(j.status)}</span></td>
						<td>
							<div class="row" style="gap: 0.3rem; flex-wrap: nowrap">
								{#if j.company}
									<form method="POST" action="?/add" use:enhance={submitting}>
										<input type="hidden" name="names" value={j.company} />
										<button class="secondary small" disabled={busy} title="Add “{j.company}” to your list and tag all its jobs">+ List</button>
									</form>
								{/if}
								<form method="POST" action="?/clear" use:enhance>
									<input type="hidden" name="job" value={j.id} />
									<button class="ghost small" title="Not a recruiter: remove the badge">✕</button>
								</form>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	.intro { max-width: 60rem; }
	.add { display: grid; gap: 0.6rem; }
	.tagged { margin: 0.4rem 0 0.2rem; padding-left: 1.2rem; }
</style>
