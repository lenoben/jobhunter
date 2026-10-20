<script lang="ts">
	// Time-series chart: lines (kind="line") or stacked columns (kind="stack"), hand-drawn SVG.
	// Hover a period for the tooltip; legend above; table view below (colours are never the only cue).
	type Series = { key: string; label: string; color: string };
	// compact: a small multiple — shorter, no table (the page has one combined table), and the
	// title carries the period total; a single series never gets a legend box (the title names it).
	let { rows, series, kind, period, title, subtitle = '', compact = false }: {
		rows: Record<string, any>[]; series: Series[]; kind: 'line' | 'stack'; period: 'day' | 'month';
		title: string; subtitle?: string; compact?: boolean;
	} = $props();

	let width = $state(640);
	const height = $derived(compact ? 130 : 220);
	const m = $derived({ top: 10, right: compact ? 10 : 44, bottom: 24, left: 30 });
	const plotW = $derived(Math.max(60, width - m.left - m.right));
	const plotH = $derived(height - m.top - m.bottom);
	let hover = $state<number | null>(null);

	const totals = $derived(rows.map((r) => (kind === 'stack' ? series.reduce((s, x) => s + (r[x.key] ?? 0), 0) : Math.max(0, ...series.map((x) => r[x.key] ?? 0)))));
	// 4 gridline steps of 1/2/5 × 10ⁿ, so every tick is a whole, round number
	function niceMax(v: number) {
		const raw = Math.max(1, v / 4);
		const p = 10 ** Math.floor(Math.log10(raw));
		const step = [1, 2, 5, 10].map((f) => f * p).find((s) => s >= raw) ?? 10 * p;
		return step * 4;
	}
	const yMax = $derived(niceMax(Math.max(1, ...totals)));
	const ticks = $derived((compact ? [0, 2, 4] : [0, 1, 2, 3, 4]).map((i) => (yMax / 4) * i));
	const band = $derived(plotW / Math.max(1, rows.length));
	const x = (i: number) => m.left + band * i + band / 2;
	const y = (v: number) => m.top + plotH - (v / yMax) * plotH;

	function label(p: string, long = false) {
		const [yy, mm, dd] = p.split('-').map(Number);
		const d = new Date(yy, mm - 1, dd || 1);
		if (period === 'month') return d.toLocaleDateString('de-DE', long ? { month: 'long', year: 'numeric' } : { month: 'short' });
		return d.toLocaleDateString('de-DE', long ? { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' } : { day: '2-digit', month: '2-digit' });
	}
	// thin the x labels to what fits: ~36px per month name ("Nov"), ~56px per date
	const every = $derived(Math.ceil(rows.length / Math.max(2, Math.floor(plotW / (period === 'month' ? 36 : 56)))));
	const fmtNum = (v: number) => (v >= 1000 ? `${+(v / 1000).toFixed(1)}K` : String(Math.round(v)));

	// column with a 4px rounded top (data end), square at the baseline
	function colPath(x0: number, y0: number, w: number, h: number, round: boolean) {
		if (h <= 0) return '';
		const r = round ? Math.min(4, w / 2, h) : 0;
		return `M${x0},${y0 + h}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + w - r}Q${x0 + w},${y0} ${x0 + w},${y0 + r}V${y0 + h}Z`;
	}
	const colW = $derived(Math.min(24, Math.max(3, band * 0.62)));
	function stack(r: Record<string, any>) {
		let acc = 0;
		const segs = series.map((s) => {
			const v = r[s.key] ?? 0;
			const seg = { s, v, from: acc, to: acc + v };
			acc += v;
			return seg;
		}).filter((g) => g.v > 0);
		return segs.map((g, i) => ({ ...g, top: i === segs.length - 1 }));
	}
	const linePath = (key: string) => rows.map((r, i) => `${i ? 'L' : 'M'}${x(i)},${y(r[key] ?? 0)}`).join('');
	// end labels only when the line ends are far enough apart (never stacked/nudged)
	const endLabels = $derived.by(() => {
		if (kind !== 'line' || !rows.length) return [];
		const last = rows[rows.length - 1];
		const ends = series.map((s) => ({ s, v: last[s.key] ?? 0, yy: y(last[s.key] ?? 0) }));
		const apart = ends.every((a, i) => ends.every((b, j) => i === j || Math.abs(a.yy - b.yy) >= 14));
		return apart ? ends : [];
	});
	const tipLeft = $derived(hover === null ? 0 : Math.min(Math.max(x(hover) - 105, 0), width - 210));
</script>

<figure class="card chart" class:compact>
	<figcaption>
		<strong>{title}</strong>{#if subtitle}<span class="muted small"> · {subtitle}</span>{/if}
		{#if series.length > 1}<div class="legend">
			{#each series as s}<span class="key"><i style="background: var({s.color})" class:line={kind === 'line'}></i>{s.label}</span>{/each}
		</div>{/if}
	</figcaption>
	<div class="plot" bind:clientWidth={width} role="img" aria-label="{title}: see the table below for the values">
		<!-- viewBox + 100% width: the server-rendered first paint already spans the card -->
		<svg width="100%" {height} viewBox="0 0 {width} {height}">
			{#each ticks as t}
				<line x1={m.left} x2={m.left + plotW} y1={y(t)} y2={y(t)} class={t === 0 ? 'base' : 'grid'} />
				<text x={m.left - 6} y={y(t) + 4} class="tick" text-anchor="end">{fmtNum(t)}</text>
			{/each}
			{#each rows as r, i}
				{#if (i % every === 0 && rows.length - 1 - i >= every) || i === rows.length - 1}
					<text x={x(i)} y={height - 8} class="tick" text-anchor="middle">{label(r.period)}</text>
				{/if}
			{/each}

			{#if kind === 'stack'}
				{#each rows as r, i}
					{#each stack(r) as g}
						<!-- 2px surface gap between segments: each segment gives up 2px at its top -->
						<path d={colPath(x(i) - colW / 2, y(g.to) + (g.top ? 0 : 2), colW, y(g.from) - y(g.to) - (g.top ? 0 : 2), g.top)}
							fill="var({g.s.color})" opacity={hover === null || hover === i ? 1 : 0.45} />
					{/each}
				{/each}
			{:else}
				{#if hover !== null}<line x1={x(hover)} x2={x(hover)} y1={m.top} y2={m.top + plotH} class="cross" />{/if}
				{#each series as s}
					<path d={linePath(s.key)} fill="none" stroke="var({s.color})" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
				{/each}
				{#each series as s}
					{@const i = hover ?? rows.length - 1}
					<circle cx={x(i)} cy={y(rows[i]?.[s.key] ?? 0)} r="4" fill="var({s.color})" stroke="var(--surface)" stroke-width="2" />
				{/each}
				{#each endLabels as e}
					<text x={x(rows.length - 1) + 8} y={e.yy + 4} class="end">{e.v}</text>
				{/each}
			{/if}

			<!-- hit targets: one full-height band per period -->
			{#each rows as _, i}
				<rect x={m.left + band * i} y={m.top} width={band} height={plotH} fill="transparent"
					role="presentation" onmouseenter={() => (hover = i)} onmouseleave={() => (hover = null)} />
			{/each}
		</svg>
		{#if hover !== null}
			{@const r = rows[hover]}
			<div class="tip" style="left: {tipLeft}px">
				<div class="small"><strong>{label(r.period, true)}</strong></div>
				{#each series as s}
					<div class="tip-row small"><i style="background: var({s.color})"></i>{s.label}<span class="grow"></span><strong>{r[s.key] ?? 0}</strong></div>
				{/each}
				{#if kind === 'stack' && series.length > 1}<div class="tip-row small muted">Total<span class="grow"></span>{totals[hover]}</div>{/if}
			</div>
		{/if}
	</div>
	{#if !compact}<details class="table-view">
		<summary class="small muted">Table</summary>
		<div class="table-wrap">
			<table>
				<thead><tr><th>{period === 'day' ? 'Day' : 'Month'}</th>{#each series as s}<th class="num">{s.label}</th>{/each}</tr></thead>
				<tbody>
					{#each [...rows].reverse() as r}
						<tr><td class="small">{label(r.period, true)}</td>{#each series as s}<td class="num small">{r[s.key] ?? 0}</td>{/each}</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</details>{/if}
</figure>

<style>
	.chart { margin: 0 0 1rem; }
	.chart.compact { margin: 0; padding-bottom: 0.4rem; }
	figcaption { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.3rem 0.8rem; margin-bottom: 0.4rem; }
	.legend { display: flex; flex-wrap: wrap; gap: 0.3rem 0.9rem; margin-left: auto; font-size: 0.85rem; color: var(--muted); }
	.key { display: inline-flex; align-items: center; gap: 0.35rem; }
	.key i, .tip-row i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; }
	.key i.line { height: 3px; width: 14px; border-radius: 2px; }
	.plot { position: relative; width: 100%; }
	svg { display: block; overflow: visible; }
	.grid { stroke: var(--grid); stroke-width: 1; }
	.base { stroke: var(--border); stroke-width: 1; }
	.cross { stroke: var(--muted); stroke-width: 1; opacity: 0.6; }
	.tick { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
	.end { fill: var(--text); font-size: 12px; font-weight: 600; }
	.tip {
		position: absolute; top: 0; width: 210px; pointer-events: none; padding: 0.45rem 0.6rem;
		background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
		box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12);
	}
	.tip-row { display: flex; align-items: center; gap: 0.4rem; margin-top: 0.15rem; }
	.grow { flex: 1; }
	.num { text-align: right; font-variant-numeric: tabular-nums; }
	.table-view { margin-top: 0.4rem; }
	.table-view summary { cursor: pointer; }
</style>
