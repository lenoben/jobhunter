<script lang="ts">
	import TimeChart from '$lib/TimeChart.svelte';

	let { data } = $props();
	const sum = (k: string) => data.rows.reduce((s: number, r: any) => s + r[k], 0);
	const range = $derived(data.period === 'day' ? 'last 30 days' : 'last 12 months');
	const tiles = $derived([
		{ label: 'Found', value: sum('found'), sub: range },
		{ label: 'Scored', value: sum('scored'), sub: range },
		{ label: 'Documents written', value: sum('docs'), sub: range },
		{ label: 'Applied', value: sum('applied'), sub: range },
		{ label: 'Feedback received', value: sum('feedback'), sub: range },
		{ label: 'Interviews / offers', value: sum('interview'), sub: range },
		{ label: 'Rejected', value: sum('rejected_only'), sub: range },
		{ label: 'Withdrawn', value: sum('withdrawn'), sub: range }
	]);
	// one small chart per status (same time axis; each has its own scale) — in pipeline order
	const STEPS: [string, string][] = [
		['found', 'Found'], ['scored', 'Scored'], ['shortlisted', 'Shortlisted'], ['skipped_fit', 'Skipped (fit/rules)'],
		['not_interested', 'Not interested (you)'], ['flagged', 'Flagged: needs you'], ['review', 'Alert jobs to review'],
		['docs', 'Documents ready'], ['applied', 'Applied'], ['feedback', 'Feedback received'], ['interview_only', 'Interview'], ['offer', 'Offer'],
		['rejected_only', 'Rejected'], ['withdrawn', 'Withdrawn']
	];
	const per = $derived(data.period === 'day' ? 'per day' : 'per month');
	const now = $derived([
		['Not scored yet', data.counts.new ?? 0, '/?status=new'],
		['Shortlisted', data.counts.shortlisted ?? 0, '/?status=shortlisted'],
		['Documents ready', data.counts.docs_ready ?? 0, '/?status=docs_ready'],
		['Applied', data.counts.applied ?? 0, '/?status=applied'],
		['Feedback received', data.counts.feedback ?? 0, '/?status=feedback'],
		['Interview',data.counts.interview ?? 0, '/?status=interview'],
		['Offer', data.counts.offer ?? 0, '/?status=offer'],
		['Rejected', data.counts.rejected ?? 0, '/?status=rejected'],
		['Withdrawn', data.counts.withdrawn ?? 0, '/?status=withdrawn'],
		['Needs you', data.counts.needs_attention ?? 0, '/attention']
	] as [string, number, string][]);
</script>

<svelte:head><title>Statistics · JobHunter</title></svelte:head>

<div class="row" style="align-items: baseline">
	<h1 style="margin-right: auto">Statistics</h1>
	<div class="seg" role="group" aria-label="Period">
		<a href="?period=day" class:on={data.period === 'day'} aria-current={data.period === 'day' ? 'page' : undefined}>Daily</a>
		<a href="?period=month" class:on={data.period === 'month'} aria-current={data.period === 'month' ? 'page' : undefined}>Monthly</a>
	</div>
</div>

<div class="tiles">
	{#each tiles as t}
		<div class="card tile"><div class="small muted">{t.label}</div><div class="value">{t.value.toLocaleString('de-DE')}</div><div class="small muted">{t.sub}</div></div>
	{/each}
</div>

<TimeChart rows={data.rows} kind="stack" period={data.period} title="Your pipeline"
	subtitle="jobs reaching each step, {data.period === 'day' ? 'per day' : 'per month'}"
	series={[
		{ key: 'docs', label: 'Documents ready', color: '--series-1' },
		{ key: 'applied', label: 'Applied', color: '--series-2' },
		{ key: 'feedback', label: 'Feedback received', color: '--series-3' },
		{ key: 'interview', label: 'Interview / offer', color: '--series-4' },
		{ key: 'rejected', label: 'Rejected / withdrawn', color: '--series-5' }
	]} />

<h2 class="section">Every status <span class="muted small">jobs reaching each status, {per} · each chart has its own scale</span></h2>
<div class="multiples">
	{#each STEPS as [key, name]}
		<TimeChart compact rows={data.rows} kind="stack" period={data.period} title={name}
			subtitle="{sum(key).toLocaleString('de-DE')} in total" series={[{ key, label: name, color: '--series-1' }]} />
	{/each}
</div>
<details class="card">
	<summary class="small"><strong>Table</strong> <span class="muted">every status, {per}</span></summary>
	<div class="table-wrap" style="margin-top: 0.5rem">
		<table>
			<thead><tr><th>{data.period === 'day' ? 'Day' : 'Month'}</th>{#each STEPS as [, name]}<th class="num small">{name}</th>{/each}</tr></thead>
			<tbody>
				{#each [...data.rows].reverse() as r}
					<tr><td class="small">{r.period}</td>{#each STEPS as [key]}<td class="num small">{(r as any)[key]}</td>{/each}</tr>
				{/each}
			</tbody>
		</table>
	</div>
</details>

<div class="card">
	<strong>Right now</strong> <span class="muted small">jobs per status today</span>
	<div class="now">
		{#each now as [l, n, href]}
			<a class="now-item" {href}><span class="small muted">{l}</span><strong>{n}</strong></a>
		{/each}
	</div>
</div>

<style>
	.seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
	.seg a { padding: 0.3rem 0.8rem; color: var(--text); font-size: 0.9rem; }
	.seg a.on { background: var(--accent); color: var(--accent-text); }
	.seg a:hover { text-decoration: none; }
	.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.7rem; margin-bottom: 1rem; }
	.tile { margin: 0; }
	.section { margin: 1.4rem 0 0.6rem; font-size: 1.1rem; }
	.multiples { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.7rem; margin-bottom: 1rem; }
	.num { text-align: right; font-variant-numeric: tabular-nums; }
	.value { font-size: 1.7rem; font-weight: 600; line-height: 1.2; margin: 0.15rem 0; }
	.now { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.5rem; margin-top: 0.6rem; }
	.now-item { display: flex; flex-direction: column; padding: 0.5rem 0.6rem; border: 1px solid var(--border); border-radius: var(--radius); color: var(--text); }
	.now-item:hover { text-decoration: none; border-color: var(--accent); }
	.now-item strong { font-size: 1.2rem; }
</style>
