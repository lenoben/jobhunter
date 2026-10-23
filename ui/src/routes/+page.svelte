<script lang="ts">
	import { enhance } from '$app/forms';
	import { label, localTime } from '$lib/format';
	import ConfirmDelete from '$lib/ConfirmDelete.svelte';

	let { data, form } = $props();
	const total = $derived(Object.values(data.counts).reduce((a: number, b: number) => a + b, 0));
	const CLOSED = ['applied', 'feedback', 'interview', 'offer', 'rejected', 'withdrawn'];

	/** Current query with some parameters replaced (page resets unless given). */
	function href(changes: Record<string, string | number>) {
		const p = new URLSearchParams();
		const cur: Record<string, string | number> = {
			q: data.params.q, status: data.params.status, source: data.params.source,
			work_mode: data.params.work_mode, fav: data.params.fav, sort: data.params.sort, dir: data.params.dir,
			size: data.pageSize, page: 1, ...changes
		};
		for (const [k, v] of Object.entries(cur)) {
			if (v !== '' && v !== undefined && !(k === 'page' && v === 1) && !(k === 'size' && v === 50)) p.set(k, String(v));
		}
		const s = p.toString();
		return s ? `?${s}` : '/';
	}

	/** Click a header: sort by it; click again: flip the direction. Fit starts high → low. */
	function sortHref(key: string) {
		if (data.params.sort === key) return href({ sort: key, dir: data.params.dir === 'asc' ? 'desc' : 'asc' });
		return href({ sort: key, dir: key === 'fit' || key === 'first_seen' ? 'desc' : 'asc' });
	}
	function arrow(key: string) {
		return data.params.sort === key ? (data.params.dir === 'asc' ? ' ▲' : ' ▼') : '';
	}

	const columns = [
		{ key: 'title', label: 'Title' },
		{ key: 'company', label: 'Company' },
		{ key: 'location', label: 'Location' },
		{ key: 'work_mode', label: 'Mode', cls: 'hide-sm' },
		{ key: 'fit', label: 'Fit' },
		{ key: 'status', label: 'Status' },
		{ key: 'first_seen', label: 'First seen', cls: 'hide-sm' }
	];
	const from = $derived(data.total ? (data.page - 1) * data.pageSize + 1 : 0);
	const to = $derived(Math.min(data.page * data.pageSize, data.total));
</script>

<svelte:head><title>Jobs · JobHunter</title></svelte:head>

<h1>Jobs <span class="muted small">{data.total} match · {total} in total</span></h1>

{#if form?.error}<div class="flash">{form.error}</div>{/if}
{#if form?.started}<div class="flash">{form.started}</div>{/if}
{#if form?.deleted || data.deleted}<div class="flash">Job deleted, with its documents.</div>{/if}
{#if data.requested > 0}
	<div class="card row" style="border-color: var(--accent)">
		<div class="grow"><strong>{data.requested}</strong> job{data.requested === 1 ? '' : 's'} waiting for documents you requested.
			<span class="muted small">They are written in the next scheduled run, or right now:</span></div>
		<form method="POST" action="?/generate" use:enhance><button>✍️ Generate now</button></form>
	</div>
{/if}
{#if (data.counts.new ?? 0) > 0}
	<div class="card row">
		<div class="grow"><strong>{data.counts.new}</strong> job{data.counts.new === 1 ? '' : 's'} not scored yet.
			<span class="muted small">Each run scores {data.maxEvaluated}; score up to 60 more now (no new search):</span></div>
		<form method="POST" action="?/score" use:enhance><button class="secondary">🧮 Score waiting jobs</button></form>
	</div>
{/if}

<details class="card" id="add-job" open={!!form?.addError || data.openAdd}>
	<summary><strong>+ Add a job</strong> <span class="muted small">by link; paste the posting for LinkedIn/Instaffo or pages that don't load ·
		<a href="/boards">your job boards</a></span></summary>
	{#if form?.addError}<div class="flash" style="margin-top: 0.6rem">{form.addError}</div>{/if}
	<form method="POST" action="?/add" style="display: grid; gap: 0.6rem; margin-top: 0.7rem">
		<input type="url" name="url" required placeholder="https://… (the job posting's link)" value={form?.addValues?.url ?? ''} />
		<div class="row">
			<input type="text" name="title" placeholder="Title (optional)" class="grow" />
			<input type="text" name="company" placeholder="Company (optional)" class="grow" />
			<input type="text" name="location" placeholder="City (optional)" class="grow" />
		</div>
		<input type="text" name="apply-to" placeholder="Where to apply (optional): application form link or email address — found in the posting text automatically if left empty" value={form?.addValues?.applyTo ?? ''} />
		<textarea name="text" rows="5" placeholder="Full posting text (optional — copy the whole ad here)">{form?.addValues?.text ?? ''}</textarea>
		<div class="row">
			<label class="checks" style="margin: 0"><input type="checkbox" name="now" checked /> Evaluate now (and write documents if it fits)</label>
			<span class="grow"></span>
			<button>Add job</button>
		</div>
	</form>
</details>

<form class="card row filters" method="GET">
	<input type="search" name="q" placeholder="Search title, company, location" value={data.params.q} class="grow" />
	<select name="status" aria-label="Status">
		<option value="open" selected={data.params.status === 'open'}>All except skipped</option>
		<option value="all" selected={data.params.status === 'all'}>All</option>
		{#each data.statuses as s}
			<option value={s} selected={data.params.status === s}>{label(s)} ({data.counts[s] ?? 0})</option>
		{/each}
	</select>
	<select name="source" aria-label="Source">
		<option value="">All sources</option>
		{#each data.sources as s}<option value={s} selected={data.params.source === s}>{s}</option>{/each}
	</select>
	<select name="work_mode" aria-label="Work mode">
		<option value="">Any work mode</option>
		{#each ['remote', 'hybrid', 'onsite', 'unknown'] as m}
			<option value={m} selected={data.params.work_mode === m}>{m}</option>
		{/each}
	</select>
	<label class="checks" style="margin: 0" title="Show only your favourites">
		<input type="checkbox" name="fav" value="1" checked={data.params.fav === '1'} /> ★ Favourites ({data.favoriteCount})
	</label>
	<input type="hidden" name="sort" value={data.params.sort} />
	<input type="hidden" name="dir" value={data.params.dir} />
	<button>Filter</button>
	<a class="button secondary" href="/">Reset</a>
</form>

<nav class="row sort-sm show-sm" aria-label="Sort">
	<span class="muted small">Sort:</span>
	{#each [['fit', 'Fit'], ['first_seen', 'Newest'], ['title', 'Title'], ['company', 'Company'], ['status', 'Status']] as [key, name]}
		<a class="button secondary small" class:on={data.params.sort === key} href={sortHref(key)}>{name}{arrow(key)}</a>
	{/each}
</nav>

<div class="table-wrap">
	<table class="stack jobs">
		<thead>
			<tr>
				<th aria-label="Favourite"></th>
				{#each columns as c}
					<th class={c.cls ?? ''} aria-sort={data.params.sort === c.key ? (data.params.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
						<a class="sort" href={sortHref(c.key)} title="Sort by {c.label}">{c.label}{arrow(c.key)}</a>
					</th>
				{/each}
				<th></th>
			</tr>
		</thead>
		<tbody>
			{#each data.rows as j (j.id)}
				<tr>
					<td class="fav-cell">
						<form method="POST" action="?/favorite" use:enhance>
							<input type="hidden" name="id" value={j.id} />
							<button class="star" class:on={j.favorite} title={j.favorite ? 'Remove from favourites' : 'Add to favourites'}
								aria-pressed={!!j.favorite}>{j.favorite ? '★' : '☆'}</button>
						</form>
					</td>
					<td class="title"><a href="/jobs/{j.id}">{j.title}</a></td>
					<td class="company">{j.company ?? '–'}</td>
					<td class="location">{j.location ?? '–'}</td>
					<td class="hide-sm">{j.work_mode ?? '–'}</td>
					<td class="score fit">{j.fit_score ?? ''}</td>
					<td class="status">
						<span class="pill s-{j.status}" title={j.attention_reason ?? ''}>{label(j.status)}</span>
						{#if j.attention_reason}<div class="muted small">{label(j.attention_reason)}</div>{/if}
						{#if j.docs_requested}<div class="muted small">✍️ documents requested</div>{/if}
					</td>
					<td class="hide-sm muted small">{localTime(j.first_seen_at)}</td>
					<td class="actions">
						<div class="row" style="gap: 0.3rem; flex-wrap: nowrap">
							{#if !CLOSED.includes(j.status) && !j.has_docs && !j.docs_requested}
								<form method="POST" action="?/docs" use:enhance>
									<input type="hidden" name="id" value={j.id} />
									<button class="secondary small" title="Write CV + cover letter for this job (next run or Generate now)">
										{j.status === 'skipped' ? 'Apply anyway' : 'Write docs'}
									</button>
								</form>
							{/if}
							{#if !CLOSED.includes(j.status) && j.status !== 'skipped'}
								<form method="POST" action="?/skip" use:enhance>
									<input type="hidden" name="id" value={j.id} />
									<button class="ghost small" title="Not interested: move to skipped">✕</button>
								</form>
							{/if}
							<ConfirmDelete action="?/delete" id={j.id} small
								question={j.has_docs || CLOSED.includes(j.status) ? 'Delete job + documents?' : 'Delete job?'} />
						</div>
					</td>
				</tr>
			{:else}
				<tr><td colspan="9" class="muted">No jobs match.</td></tr>
			{/each}
		</tbody>
	</table>
</div>

<nav class="row pager" aria-label="Pages">
	<span class="muted small">{from}–{to} of {data.total}</span>
	<span class="grow"></span>
	{#if data.page > 1}<a class="button secondary" href={href({ page: data.page - 1 })}>← Prev</a>{/if}
	<span class="small">Page {data.page} / {data.pages}</span>
	{#if data.page < data.pages}<a class="button secondary" href={href({ page: data.page + 1 })}>Next →</a>{/if}
	<span class="small muted">Per page:</span>
	{#each data.pageSizes as n}
		<a href={href({ size: n })} class:active-size={n === data.pageSize}>{n}</a>
	{/each}
</nav>

<style>
	.sort { color: inherit; display: block; white-space: nowrap; }
	.sort:hover { color: var(--accent); text-decoration: none; }
	.pager { margin-top: 0.8rem; }
	.active-size { font-weight: 700; text-decoration: underline; }
	.fav-cell { width: 1.8rem; padding-right: 0; }
	.filters input[type='search'] { flex: 1 1 16rem; }
	.sort-sm { margin-bottom: 0.6rem; gap: 0.35rem; }
	.sort-sm .button { padding: 0.15rem 0.55rem; font-size: 0.82rem; }
	.sort-sm .on { border-color: var(--accent); color: var(--accent); }

	/* phone: one card per job — ☆ title · fit / company · city / status … buttons */
	@media (max-width: 700px) {
		.sort-sm { display: flex; }
		.filters select { flex: 1 1 9rem; }
		.filters button, .filters .button { flex: 1 1 auto; text-align: center; }
		.jobs .fav-cell { width: auto; }
		.jobs .title { flex: 1 1 calc(100% - 6rem); font-weight: 600; }
		.jobs .fit::before { content: 'Fit '; color: var(--muted); font-weight: 400; font-size: 0.8rem; }
		.jobs .company { order: 1; margin-left: 1.9rem; color: var(--muted); }
		.jobs .location { order: 1; flex: 1 1 auto; color: var(--muted); font-size: 0.9rem; }
		.jobs .location::before { content: '· '; }
		.jobs .status { order: 2; margin-left: 1.9rem; flex: 1 1 auto; }
		.jobs .actions { order: 2; margin-left: auto; }
	}
</style>
