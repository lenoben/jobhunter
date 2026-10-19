<script lang="ts">
	import { enhance } from '$app/forms';
	import { ATTENTION_HELP, label, localTime } from '$lib/format';
	import InferredFacts from '$lib/InferredFacts.svelte';

	let { data, form } = $props();
	let picked = $state<number[]>([]);
	const allPicked = $derived(data.review.length > 0 && picked.length === data.review.length);
	function toggleAll() {
		picked = allPicked ? [] : data.review.map((j: any) => j.id);
	}
</script>

<svelte:head><title>Needs you · JobHunter</title></svelte:head>

<h1>Needs you <span class="muted small">{data.jobs.length}{data.review.length ? ` · ${data.review.length} alert jobs to review` : ''}</span></h1>
{#if form?.error}<div class="flash">{form.error}</div>{/if}
{#if form?.reviewed}<div class="flash">{form.reviewed}</div>{/if}

{#if data.review.length}
	<details class="card" id="review" open>
		<summary><strong>📥 Job-alert jobs to review</strong>
			<span class="muted small">{data.review.length} from your alert emails match none of your filters' keywords. Tick the ones
				worth a look: they get evaluated (fit score, documents if they fit). Nothing is evaluated until you choose.</span></summary>
		<form method="POST" action="?/review" use:enhance={() => async ({ update }) => { await update(); picked = []; }}>
			<div class="row" style="margin: 0.7rem 0">
				<label class="checks" style="margin: 0"><input type="checkbox" checked={allPicked} onchange={toggleAll} /> Select all</label>
				<span class="muted small">{picked.length} selected</span>
				<span class="grow"></span>
				<button name="decision" value="evaluate" class="secondary" disabled={!picked.length}>Evaluate in next run</button>
				<button name="decision" value="evaluate_now" disabled={!picked.length} title="Scores them right away (no new search)">🧮 Evaluate now</button>
				<button name="decision" value="skip" class="ghost" disabled={!picked.length}>Not interested</button>
			</div>
			<div class="table-wrap">
				<table class="stack">
					<thead><tr><th></th><th>Title</th><th>Company</th><th class="hide-sm">Location</th><th class="hide-sm">Received</th></tr></thead>
					<tbody>
						{#each data.review as j (j.id)}
							<tr>
								<td><input type="checkbox" name="id" value={j.id} bind:group={picked} aria-label="Select {j.title}" /></td>
								<td class="fill"><a href="/jobs/{j.id}">{j.title}</a>
									<a class="muted small" href={j.url} target="_blank" rel="noopener noreferrer" title="Open the posting">↗</a></td>
								<td class="full indent">{j.company ?? '–'}<span class="show-sm muted">{j.location ? ` · ${j.location}` : ''}</span></td>
								<td class="hide-sm">{j.location ?? '–'}{j.work_mode ? ` · ${j.work_mode}` : ''}</td>
								<td class="hide-sm muted small">{j.posted_at ?? localTime(j.first_seen_at)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</form>
	</details>
{/if}

{#each data.jobs as j (j.id)}
	<div class="card">
		<div class="row">
			<a href="/jobs/{j.id}"><strong>{j.title}</strong></a>
			<span class="muted">– {j.company ?? '?'}, {j.location ?? '?'}</span>
			<span class="grow"></span>
			<span class="pill s-needs_attention">{label(j.attention_reason)}</span>
		</div>
		<p class="small">{ATTENTION_HELP[j.attention_reason] ?? ''}</p>
		{#if j.detail}<p class="small muted">{j.detail}</p>{/if}

		{#if j.attention_reason === 'inferred_facts' && j.inferred?.length}
			<InferredFacts facts={j.inferred} action="/jobs/{j.id}" />
		{:else}
			<div class="row">
				<form method="POST" action="/jobs/{j.id}?/status" use:enhance>
					{#if j.fit_score === null}
						<!-- never evaluated (screening flagged it during search) → let the next run evaluate it -->
						<input type="hidden" name="status" value="new" />
						<input type="hidden" name="note" value="resolved by user: evaluate it" />
						<button class="secondary" title="The next run evaluates it">Pursue anyway → evaluate</button>
					{:else}
						<input type="hidden" name="status" value="shortlisted" />
						<input type="hidden" name="note" value="resolved by user (from Needs you)" />
						<button class="secondary" title="The next run tailors documents for it">Resolved → shortlist</button>
					{/if}
				</form>
				<a class="button secondary" href="/jobs/{j.id}">Open</a>
			</div>
		{/if}
		<div class="row" style="margin-top: 0.5rem">
			<form method="POST" action="/jobs/{j.id}?/skip" use:enhance>
				<button class="ghost small">Not interested</button>
			</form>
			<span class="muted small">flagged {localTime(j.updated_at)}{j.fit_score !== null ? ` · fit ${j.fit_score}` : ''}</span>
		</div>
	</div>
{:else}
	<p class="muted">Nothing needs you right now. 🎉</p>
{/each}
