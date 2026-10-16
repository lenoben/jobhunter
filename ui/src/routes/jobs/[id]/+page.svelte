<script lang="ts">
	import { enhance } from '$app/forms';
	import { ATTENTION_HELP, label, localTime } from '$lib/format';
	import InferredFacts from '$lib/InferredFacts.svelte';
	import CopyButton from '$lib/CopyButton.svelte';

	let { data, form } = $props();
	const job = $derived(data.job);
	const app = $derived(data.application);
	const pending = $derived(job.status === 'needs_attention' && job.attention_reason === 'inferred_facts');
	const closed = $derived(['skipped', 'applied', 'interview', 'offer', 'rejected', 'withdrawn'].includes(job.status));
</script>

<svelte:head><title>{job.title} · JobHunter</title></svelte:head>

<p class="small"><a href="/">← Jobs</a></p>
<h1>{job.title}</h1>
<p class="muted">
	{job.company ?? '–'} · {job.location ?? '–'} · {job.work_mode ?? 'work mode unknown'}
	{#if job.employment_type}· {label(job.employment_type)}{/if}
	{#if job.language}· posting in {job.language}{/if}
</p>

{#if form?.error}<div class="flash">{form.error}</div>{/if}
{#if data.added}<div class="flash">{data.added === 'new' ? 'Job added.' : 'This job was already in your list.'}
	{#if data.evaluating} It is being evaluated now: reload in 1–3 minutes to see the fit score (and documents if it fits).{/if}</div>{/if}
{#if form?.started && form?.fromPosting}<div class="flash">{form.started}</div>{/if}
{#if form?.postingSaved}<div class="flash">Posting saved. The job is {form.postingSaved === 'new' ? 'evaluated again in the next run' : `now "${form.postingSaved}"`}.</div>{/if}

<div class="card">
	<div class="row">
		<span class="pill s-{job.status}">{label(job.status)}</span>
		{#if job.attention_reason}<strong>{label(job.attention_reason)}</strong>{/if}
		{#if job.fit_score !== null}<span>Fit <span class="score">{job.fit_score}</span>/100</span>{/if}
		<span class="grow"></span>
		<a class="button secondary" href={job.url} target="_blank" rel="noopener noreferrer">Open posting ↗</a>
	</div>
	{#if job.attention_reason}<p class="small">{ATTENTION_HELP[job.attention_reason] ?? ''}</p>{/if}

	<div class="row" style="margin-top: 0.8rem">
		<form method="POST" action="?/status" use:enhance class="row grow">
			<select name="status" aria-label="New status">
				{#each data.statuses as s}<option value={s} selected={s === job.status}>{label(s)}</option>{/each}
			</select>
			<input type="text" name="note" placeholder="Note (optional)" class="grow" />
			<button>Set status</button>
		</form>
	</div>
	<div class="row" style="margin-top: 0.6rem">
		{#if !closed}
			<form method="POST" action="?/applied" use:enhance><button class="secondary">✓ Mark as applied</button></form>
			<form method="POST" action="?/skip" use:enhance><button class="secondary">Not interested</button></form>
		{/if}
		{#if app?.applied_at}<span class="muted small">Applied {localTime(app.applied_at)}</span>{/if}
	</div>
</div>

{#if pending && app?.inferred_facts?.length}
	<div class="card" style="border-color: var(--warn)">
		<h2 style="margin-top: 0">Inferred facts: your approval needed</h2>
		<InferredFacts facts={app.inferred_facts} />
	</div>
{/if}

<div class="card">
	<h2 style="margin-top: 0">Documents</h2>
	{#if form?.started}<div class="flash">{form.started}</div>{/if}
	{#if form?.requested}<div class="flash">Requested. The next run writes them, or press "Generate now".</div>{/if}
	{#if !closed}
		<form method="POST" action="?/docs" use:enhance class="row" style="margin-bottom: 0.7rem">
			<span class="small">
				{#if job.docs_requested}✍️ Requested: <strong>{data.docChoices[job.docs_requested]}</strong>. Change:
				{:else if data.documents.length}Write again:
				{:else if job.status === 'skipped'}Skipped, but you can still apply:
				{:else if (job.fit_score ?? 0) < data.docThreshold}Fit below {data.docThreshold}, so no automatic documents. Write them anyway:
				{:else}Write documents:{/if}
			</span>
			<select name="which" aria-label="Which documents">
				{#each Object.entries(data.docChoices) as [k, v]}
					<option value={k} selected={(job.docs_requested ?? 'both') === k}>{v}</option>
				{/each}
			</select>
			<button class="secondary" name="now" value="0">{job.status === 'skipped' ? 'Apply anyway' : 'Next run'}</button>
			<button name="now" value="1" title="Starts a short documents-only run right away">✍️ Generate now</button>
		</form>
	{/if}
	{#if data.documents.length}
		<div class="row">
			{#each data.documents as d}
				<a class="button secondary" href="/files/{job.id}/{d.name}" target="_blank">📄 {d.label}</a>
			{/each}
		</div>
		{#if app?.method}<p class="small">How to apply: {app.method}</p>{/if}
		{#if app?.email_draft_saved}<p class="small">✉️ Email draft saved in your mailbox (not sent).</p>{/if}
	{:else}
		<p class="muted">No documents yet.</p>
	{/if}
</div>

<div class="card">
	<h2 style="margin-top: 0">Facts</h2>
	<p class="small">
		Salary: {job.salary_text ?? 'not stated'}
		{#if job.salary_annual_eur}(≈ €{Math.round(job.salary_annual_eur).toLocaleString('de-DE')}/year){/if}
		{#if job.salary_flag}· <span class="pill">{label(job.salary_flag)}</span>{/if}
		· Apply via: {job.apply_method ?? '?'} {job.apply_email ?? ''}
		· Source: {job.source} · Posted: {job.posted_at ?? '?'} · First seen: {localTime(job.first_seen_at)}
	</p>
	{#if data.fitNotes}
		<h2>Fit notes</h2>
		<div class="prose">{@html data.fitNotes}</div>
	{/if}
</div>

{#if data.documents.length && !['skipped', 'rejected', 'withdrawn'].includes(job.status)}
	{@const kit = data.kit}
	<div class="card" id="apply-kit">
		<h2 style="margin-top: 0">Apply kit</h2>
		<p class="small muted" style="margin-top: 0">For filling in the form yourself or with the Claude browser extension.
			You log in, solve CAPTCHAs, answer work-authorization questions and click submit.</p>

		<div class="row" style="margin-bottom: 0.6rem">
			<a class="button" href={kit.url} target="_blank" rel="noopener noreferrer">Open application page ↗</a>
			{#if kit.applyEmail}<span class="small">or by email: <strong>{kit.applyEmail}</strong></span> <CopyButton text={kit.applyEmail} />{/if}
		</div>

		<h3 class="kit-h">Files to upload</h3>
		{#each kit.documents as d}
			<div class="row kit-row">
				<a href="/files/{job.id}/{d.name}" target="_blank">📄 {d.label}</a>
				<code class="grow small path">{d.path}</code>
				<CopyButton text={d.path} label="Copy path" />
			</div>
		{/each}

		<h3 class="kit-h">Form fields</h3>
		<div class="table-wrap">
			<table>
				<tbody>
					{#each kit.fields as f}
						<tr>
							<td class="small muted" style="width: 30%">{f.label}</td>
							<td class="small">{f.value}</td>
							<td style="width: 1%"><CopyButton text={f.value} /></td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<h3 class="kit-h">Prompt for the Claude browser extension</h3>
		<textarea readonly rows="8" class="small" style="font-family: ui-monospace, Consolas, monospace">{kit.prompt}</textarea>
		<div class="row" style="margin-top: 0.4rem"><CopyButton text={kit.prompt} label="Copy prompt" /></div>

		<h3 class="kit-h">The form demands unrestricted work authorization?</h3>
		<form method="POST" action="?/workauth" use:enhance class="row">
			<input type="text" name="note" placeholder='Exact wording, e.g. "uneingeschränkte Arbeitserlaubnis"' class="grow" />
			<button class="danger">Flag: work authorization</button>
		</form>
		<p class="small muted" style="margin-bottom: 0">Leave those questions empty; the job moves to <em>Needs you</em> so you can decide.</p>
	</div>
{/if}

{#if job.project_suggestions?.length}
	<div class="card">
		<h2 style="margin-top: 0">Project suggestions <span class="muted small">(R11: ideas to close the gaps; not in the documents)</span></h2>
		<div class="table-wrap">
			<table>
				<thead><tr><th>Project</th><th>Scope</th><th>Days</th><th>Covers</th></tr></thead>
				<tbody>
					{#each job.project_suggestions as p}
						<tr><td><strong>{p.title}</strong></td><td class="small">{p.scope}</td><td class="score">{p.days}</td><td class="small">{p.covers}</td></tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="muted small" style="margin-bottom: 0">Once you've built one, add it to <code>projects</code> in profile.yaml so documents can use it.</p>
	</div>
{/if}

{#if data.notes}
	<details class="card" open>
		<summary><strong>notes.md</strong> (fit, emphasis, interview prep)</summary>
		<div class="prose">{@html data.notes}</div>
	</details>
{/if}

<details class="card" open={!job.description || (job.description?.length ?? 0) < 600}>
	<summary><strong>Full posting</strong>
		{#if !job.description || job.description.length < 600}<span class="pill s-needs_attention">short / missing: add the full ad</span>{/if}</summary>
	<div class="description" style="margin: 0.6rem 0">{job.description ?? 'No description.'}</div>
	{#if !closed}
		<form method="POST" action="?/posting" use:enhance style="display: grid; gap: 0.5rem">
			<label for="posting">Paste the full job ad (replaces the text above; the job is then evaluated again)</label>
			<textarea id="posting" name="text" rows="6" placeholder="Copy the complete posting from the company's or board's page here"></textarea>
			<div class="row">
				<span class="grow"></span>
				<button class="secondary" name="now" value="0">Save posting</button>
				<button name="now" value="1" title="Haiku evaluates it now; Sonnet writes the documents if it fits">Save &amp; evaluate now</button>
			</div>
		</form>
	{/if}
</details>

<div class="card">
	<h2 style="margin-top: 0">History</h2>
	<div class="table-wrap">
		<table>
			<thead><tr><th>When</th><th>Change</th><th>By</th><th>Note</th></tr></thead>
			<tbody>
				{#each data.history as h}
					<tr>
						<td class="small muted">{localTime(h.changed_at)}</td>
						<td class="small">{h.from_status ? label(h.from_status) + ' → ' : ''}{label(h.to_status)}</td>
						<td class="small">{h.changed_by}</td>
						<td class="small">{h.note ?? ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
