<script lang="ts">
	import { enhance } from '$app/forms';
	import { ATTENTION_HELP, label, localTime } from '$lib/format';
	import InferredFacts from '$lib/InferredFacts.svelte';

	let { data } = $props();
</script>

<svelte:head><title>Needs you · JobHunter</title></svelte:head>

<h1>Needs you <span class="muted small">{data.jobs.length}</span></h1>

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
