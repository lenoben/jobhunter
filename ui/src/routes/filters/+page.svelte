<script lang="ts">
	import { enhance } from '$app/forms';

	let { data } = $props();
</script>

<svelte:head><title>Filters · JobHunter</title></svelte:head>

<div class="row">
	<h1 class="grow">Search filters</h1>
	<a class="button" href="/filters/new">+ New filter</a>
</div>
<p class="muted small">The next run uses whatever is saved here.</p>

<div class="table-wrap">
	<table>
		<thead>
			<tr><th>Active</th><th>Name</th><th>Keywords</th><th class="hide-sm">Where</th><th class="hide-sm">Min fit</th><th></th></tr>
		</thead>
		<tbody>
			{#each data.filters as f (f.id)}
				<tr>
					<td>
						<form method="POST" action="?/toggle" use:enhance>
							<input type="hidden" name="id" value={f.id} />
							<button class="small {f.active ? '' : 'secondary'}" title="Toggle active">{f.active ? 'On' : 'Off'}</button>
						</form>
					</td>
					<td><a href="/filters/{f.id}">{f.name}</a></td>
					<td class="small">{f.keywords.join(', ')}</td>
					<td class="hide-sm small">{f.location ? `${f.location} (+${f.radius_km} km), ` : ''}{f.where}</td>
					<td class="hide-sm score">{f.min_fit_score}</td>
					<td>
						<form method="POST" action="?/delete" use:enhance={({ cancel }) => {
							if (!confirm(`Delete filter "${f.name}"? Jobs found by it are kept.`)) cancel();
						}}>
							<input type="hidden" name="id" value={f.id} />
							<button class="danger small">Delete</button>
						</form>
					</td>
				</tr>
			{:else}
				<tr><td colspan="6" class="muted">No filters. Create one, or run <code>uv run python cli.py seed-filters</code>.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
