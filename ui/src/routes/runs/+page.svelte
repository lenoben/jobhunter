<script lang="ts">
	import { localTime } from '$lib/format';

	let { data } = $props();

	/** One line per source: in how many of its filter searches it had problems (mirrors
	 *  core/runs.source_problems). "no results" for some filters is normal, not a failure. */
	function grouped(errors: { source: string; message: string; filter_id?: number }[], searches: Record<string, number>) {
		const m = new Map<string, { message: string; ids: Set<string>; soft: boolean }>();
		errors.forEach((e, i) => {
			const g = m.get(e.source) ?? { message: e.message, ids: new Set<string>(), soft: true };
			g.ids.add(String(e.filter_id ?? `#${i}`));
			if (!e.message.startsWith('returned no results')) { g.soft = false; g.message = e.message; }
			m.set(e.source, g);
		});
		return [...m.entries()].map(([source, g]) => {
			const failed = g.ids.size;
			const of = Math.max(searches?.[source] ?? 0, failed);
			const kind = source === 'run' ? 'run' : failed >= of ? 'failed' : g.soft ? 'no results' : 'errors';
			return { source, message: g.message, failed, of, kind };
		});
	}
</script>

<svelte:head><title>Runs · JobHunter</title></svelte:head>

<h1>Runs</h1>
<div class="table-wrap">
	<table class="stack">
		<thead>
			<tr><th>#</th><th>Started</th><th class="hide-sm">Finished</th><th>Trigger</th><th>Status</th>
				<th>Found</th><th>New</th><th>Docs</th><th>Need you</th><th>Errors</th></tr>
		</thead>
		<tbody>
			{#each data.runs as r (r.id)}
				<tr>
					<td><strong>#{r.id}</strong></td>
					<td class="small">{localTime(r.started_at)}</td>
					<td class="small hide-sm">{localTime(r.finished_at)}</td>
					<td class="small">{r.trigger}</td>
					<td class="grow"><span class="pill {r.status === 'ok' ? 's-docs_ready' : r.status === 'failed' ? 's-rejected' : r.status === 'partial' ? 's-needs_attention' : ''}">{r.status}</span></td>
					<td class="score" data-label="Found">{r.found}</td>
					<td class="score" data-label="New">{r.new_jobs}</td>
					<td class="score" data-label="Docs">{r.tailored}</td>
					<td class="score" data-label="Need you">{r.needs_you}</td>
					<td class="small full">
						{#each grouped(r.errors, r.source_searches) as g}
							<div>
								{g.kind === 'failed' || g.kind === 'run' ? '❌' : '⚠️'}
								<strong>{g.source.replace('jobspy:', '')}</strong>
								{#if g.kind === 'no results'}no results for {g.failed} of {g.of} filters
								{:else if g.kind === 'errors'}errors in {g.failed} of {g.of} filters: <span class="muted">{g.message}</span>
								{:else}<span class="muted">{g.message}</span>{/if}
							</div>
						{/each}
					</td>
				</tr>
			{:else}
				<tr><td colspan="10" class="muted">No runs yet.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
