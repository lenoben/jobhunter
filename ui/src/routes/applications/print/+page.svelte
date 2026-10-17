<script lang="ts">
	let { data } = $props();
</script>

<svelte:head><title>Nachweis der Eigenbemühungen{data.name ? ` – ${data.name}` : ''}</title></svelte:head>

<div class="no-print row" style="margin-bottom: 1rem">
	<a href="/applications">← Applications</a>
	<span class="grow"></span>
	<span class="muted small">In the print dialog choose "Save as PDF"; landscape fits best.</span>
	<button onclick={() => window.print()}>🖨 Print / save as PDF</button>
</div>

<article class="record" lang="de">
	<h1>Nachweis der Eigenbemühungen</h1>
	<p>
		{#if data.name}Name: <strong>{data.name}</strong><br />{/if}
		{#if data.period}Zeitraum: {data.period}<br />{/if}
		Anzahl der Bewerbungen: {data.rows.length}
	</p>
	<table>
		<thead>
			<tr><th>Nr.</th>{#each data.columns as [, h]}<th>{h}</th>{/each}</tr>
		</thead>
		<tbody>
			{#each data.rows as r, i}
				<tr>
					<td>{i + 1}</td>
					{#each data.columns as [k]}
						<td>{r[k]}{#if k === 'title' && r.link}<div class="link">{r.link}</div>{/if}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
	<p class="foot">Erstellt am {data.created}</p>
</article>

<style>
	.record { background: #fff; color: #111; padding: 1.5rem; border-radius: 6px; font-size: 0.85rem; }
	.record h1 { font-size: 1.3rem; margin: 0 0 0.6rem; }
	.record table { width: 100%; border-collapse: collapse; }
	.record th, .record td { border: 1px solid #999; padding: 0.3rem 0.4rem; text-align: left; vertical-align: top; color: #111; background: #fff; }
	.record th { background: #eee; font-weight: 600; }
	.record .link { color: #555; font-size: 0.7rem; word-break: break-all; }
	.record .foot { margin-top: 1rem; color: #555; }
	@media print {
		:global(header), .no-print { display: none !important; }
		:global(body), :global(main) { background: #fff !important; padding: 0 !important; margin: 0 !important; max-width: none !important; }
		.record { padding: 0; font-size: 9pt; }
		.record tr { break-inside: avoid; }
		@page { size: A4 landscape; margin: 12mm; }
	}
</style>
