<script lang="ts">
	import { label, localTime } from '$lib/format';

	let { data } = $props();
	const counts = $derived(data.rows.reduce((m: Record<string, number>, r: any) => ((m[r.status] = (m[r.status] ?? 0) + 1), m), {}));
	const due = $derived(data.rows.filter((r: any) => r.followup === 'due' || r.followup === 'no_reply').length);
	const q = $derived(data.query ? `?${data.query}` : '');
</script>

<svelte:head><title>Applications · JobHunter</title></svelte:head>

<h1>Applications <span class="muted small">{data.rows.length} {data.from || data.to ? 'in this period' : 'in total'}</span></h1>

<form method="GET" class="card row">
	<label for="from" class="small">From</label>
	<input id="from" type="date" name="from" value={data.from ?? ''} />
	<label for="to" class="small">to</label>
	<input id="to" type="date" name="to" value={data.to ?? ''} />
	<button>Show</button>
	{#if data.from || data.to}<a class="button secondary" href="/applications">All</a>{/if}
	<span class="grow"></span>
	<a class="button secondary" href="/applications/export.csv{q}" download>⬇ CSV (Excel)</a>
	<a class="button" href="/applications/print{q}" target="_blank">🖨 Record for the Agentur (PDF)</a>
</form>

<p class="muted small">
	{#each Object.entries(counts) as [s, n], i}{i ? ' · ' : ''}{n} {label(s)}{/each}
	{#if due} · <strong>{due} waiting for a follow-up</strong>{/if}
	{#if data.after}· Follow-up reminders after {data.after} days, "no reply" after {data.silent} days (Settings).{/if}
</p>
<p class="muted small">The record lists date, employer, job, place, how and where you applied, and the outcome, in
	German, as asked for as proof of your own job search (Eigenbemühungen). Check it before handing it in.</p>

{#if data.rows.length}
	<div class="card apps" style="padding: 0; overflow-x: auto">
		<table class="stack">
			<thead>
				<tr><th>Applied</th><th>Job</th><th class="hide-sm">How / where found</th><th>Status</th><th>Follow-up</th></tr>
			</thead>
			<tbody>
				{#each data.rows as r}
					<tr>
						<td class="small">{localTime(r.applied_at).split(',')[0]}<div class="muted">{r.days} days ago</div></td>
						<td class="full first"><a href="/jobs/{r.id}">{r.title}</a><div class="muted small">{r.company ?? '–'}{r.location ? ` · ${r.location}` : ''}</div></td>
						<td class="hide-sm small">{r.methodLabel}<div class="muted">{r.sourceLabel}</div></td>
						<td><span class="pill s-{r.status}">{label(r.status)}</span>
							{#if r.status !== 'applied' && r.status_at}<div class="muted small">{localTime(r.status_at).split(',')[0]}</div>{/if}</td>
						<td class="small">
							{#if r.followup === 'due'}<a href="/jobs/{r.id}#followup">📬 due</a>
							{:else if r.followup === 'no_reply'}<a href="/jobs/{r.id}#followup">🔕 no reply</a>
							{:else if r.followup === 'done'}<span class="muted">✓ {localTime(r.followed_up_at).split(',')[0]}</span>
							{:else}<span class="muted">–</span>{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else}
	<p class="muted">No applications {data.from || data.to ? 'in this period' : 'yet'}. "Mark as applied" on a job page adds it here.</p>
{/if}
