<script lang="ts">
	import { enhance } from '$app/forms';
	import { ATTENTION_HELP, label, localTime } from '$lib/format';
	import InferredFacts from '$lib/InferredFacts.svelte';
	import CopyButton from '$lib/CopyButton.svelte';

	let { data, form } = $props();
	const job = $derived(data.job);
	const app = $derived(data.application);
	const pending = $derived(job.status === 'needs_attention' && job.attention_reason === 'inferred_facts');
	const closed = $derived(['skipped', 'applied', 'feedback', 'interview', 'offer', 'rejected', 'withdrawn'].includes(job.status));
</script>

<svelte:head><title>{job.title} · JobHunter</title></svelte:head>

<p class="small"><a href="/">← Jobs</a></p>
<h1 class="row" style="gap: 0.4rem; flex-wrap: nowrap; align-items: flex-start">
	<form method="POST" action="?/favorite" use:enhance>
		<button class="star" class:on={job.favorite} title={job.favorite ? 'Remove from favourites' : 'Add to favourites'}
			aria-pressed={!!job.favorite} style="font-size: 1.6rem">{job.favorite ? '★' : '☆'}</button>
	</form>
	<span>{job.title}</span>
</h1>
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
		{#if job.fit_score !== null}<span>Fit <span class="score">{job.fit_score}</span>/100</span>
		{:else}<span class="muted small">not scored yet</span>{/if}
		<span class="grow"></span>
		<a class="button secondary" href={job.url} target="_blank" rel="noopener noreferrer">Open posting ↗</a>
		{#if job.apply_url}<a class="button" href={job.apply_url} target="_blank" rel="noopener noreferrer">Apply here ↗</a>{/if}
	</div>
	{#if form?.reevaluating}<div class="flash" style="margin-top: 0.6rem">{form.reevaluating}</div>{/if}
	{#if job.status !== 'new' || job.fit_score !== null}
		<form method="POST" action="?/reevaluate" use:enhance class="row" style="margin-top: 0.6rem">
			<button class="secondary" title="Score this job again with the posting text it already has">🧮 {job.fit_score === null ? 'Score now' : 'Re-evaluate'}</button>
			<span class="muted small">{job.status === 'skipped'
				? 'Evaluated again from the current posting text; it can be shortlisted (documents if the fit reaches the threshold).'
				: 'New fit score and notes from the current posting text; status and documents stay as they are.'}</span>
		</form>
	{/if}
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

<div class="card" id="my-notes">
	<h2 style="margin-top: 0">My notes</h2>
	{#if form?.notesSaved}<div class="flash">Notes saved.</div>{/if}
	<form method="POST" action="?/usernotes" use:enhance={() => async ({ update }) => update({ reset: false })}>
		<textarea name="notes" rows="6" class="user-notes" aria-label="My notes on this application"
			placeholder={'e.g. 22.10. called Ms Weber (HR), interview likely in November\nContact: weber@company.de\nNext: send references'}
			>{job.user_notes ?? ''}</textarea>
		<div class="row" style="margin-top: 0.5rem">
			<button class="secondary">Save notes</button>
			<span class="muted small">{job.user_notes_at ? `Last saved ${localTime(job.user_notes_at)}` : 'Only for you; never used in the documents.'}</span>
		</div>
	</form>
</div>

{#if data.followup}
	{@const f = data.followup}
	<div class="card" id="followup" style={f.due || f.noResponse ? 'border-color: var(--warn)' : ''}>
		<h2 style="margin-top: 0">Follow-up</h2>
		<p class="small" style="margin-top: 0">
			Applied {f.days} {f.days === 1 ? 'day' : 'days'} ago, no reply recorded yet.
			{#if f.followedUpAt}You followed up on {localTime(f.followedUpAt).split(',')[0]}.
			{:else if f.due}Time for a short, polite follow-up.
			{:else if f.after}A reminder comes after {f.after} days.{/if}
			{#if f.noResponse}<br /><strong>No reply for {f.days} days.</strong> If you don't expect one any more, set the
				status above to "rejected" (or "withdrawn" if you lost interest).{/if}
		</p>
		{#if form?.followedUp}<div class="flash">Recorded. No more follow-up reminders for this job.</div>{/if}
		<div class="row">
			<form method="POST" action="?/followuptext" use:enhance><button class="secondary">✉️ Show follow-up text</button></form>
			{#if !f.followedUpAt}
				<form method="POST" action="?/followedup" use:enhance><button class="secondary">✓ I followed up</button></form>
			{/if}
		</div>
		{#if form?.followupText}
			{@const t = form.followupText}
			<div class="row" style="margin-top: 0.8rem">
				<strong class="small">Subject:</strong> <span class="small grow">{t.subject}</span>
				<CopyButton text={t.subject} label="Copy subject" />
			</div>
			<pre class="small" style="white-space: pre-wrap; margin: 0.5rem 0">{t.body}</pre>
			<div class="row">
				<CopyButton text={t.body} label="Copy text" />
				{#if job.apply_email}
					<a class="button secondary small" href="mailto:{job.apply_email}?subject={encodeURIComponent(t.subject)}&body={encodeURIComponent(t.body)}">Open in mail app</a>
				{/if}
				<span class="muted small">Send it yourself (JobHunter never sends email), then press "I followed up".</span>
			</div>
		{/if}
	</div>
{/if}


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
					<option value={k} selected={(job.docs_requested ?? data.docDefault) === k}>{v}</option>
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
		· Apply via: {job.apply_method ?? '?'}
		· Source: {job.source} · Posted: {job.posted_at ?? '?'} · First seen: {localTime(job.first_seen_at)}
	</p>
	{#if form?.applySaved}<div class="flash">{form.applySaved}</div>{/if}
	<h2>Where to apply</h2>
	{#if job.apply_url || job.apply_email || job.apply_address}
		<div class="places">
			{#if job.apply_url}<div class="place"><span class="small muted">Online</span>
				<a href={job.apply_url} target="_blank" rel="noopener noreferrer">Apply here ↗</a></div>{/if}
			{#if job.apply_email}<div class="place"><span class="small muted">Email</span>
				<span class="row" style="gap: 0.4rem"><a href="mailto:{job.apply_email}">{job.apply_email}</a><CopyButton text={job.apply_email} /></span></div>{/if}
			{#if job.apply_address}<div class="place"><span class="small muted">By post</span>
				<span class="row" style="gap: 0.4rem; align-items: flex-start"><span class="address">{job.apply_address}</span><CopyButton text={job.apply_address} /></span></div>{/if}
		</div>
	{:else}
		<p class="small muted">Nothing found in the posting. Add what it names below (one, two or all three).</p>
	{/if}
	<details open={!(job.apply_url || job.apply_email || job.apply_address)}>
		<summary class="small">Edit</summary>
		<form method="POST" action="?/applyto" use:enhance class="apply-form">
			<label class="small" for="apply-url">Application link</label>
			<input id="apply-url" type="url" name="url" value={job.apply_url ?? ''} placeholder="https://…" />
			<label class="small" for="apply-email">Email address</label>
			<input id="apply-email" type="email" name="email" value={job.apply_email ?? ''} placeholder="jobs@company.de" />
			<label class="small" for="apply-address">Postal address</label>
			<textarea id="apply-address" name="address" rows="4" placeholder={'Company GmbH\nPersonalabteilung\nStraße 1\n12345 Stadt'}>{job.apply_address ?? ''}</textarea>
			<div><button class="secondary">Save</button> <span class="small muted">An empty field removes that entry.</span></div>
		</form>
	</details>
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

		{#if data.workPermitChecks}
		<h3 class="kit-h">The form demands unrestricted work authorization?</h3>
		<form method="POST" action="?/workauth" use:enhance class="row">
			<input type="text" name="note" placeholder='Exact wording, e.g. "uneingeschränkte Arbeitserlaubnis"' class="grow" />
			<button class="danger">Flag: work authorization</button>
		</form>
		<p class="small muted" style="margin-bottom: 0">Leave those questions empty; the job moves to <em>Needs you</em> so you can decide.</p>
		{/if}
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

<style>
	.places { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.6rem; margin-bottom: 0.6rem; }
	.place { display: flex; flex-direction: column; gap: 0.25rem; padding: 0.5rem 0.6rem; border: 1px solid var(--border); border-radius: var(--radius); min-width: 0; }
	.place a { overflow-wrap: anywhere; }
	.address { white-space: pre-line; }
	.user-notes { width: 100%; box-sizing: border-box; resize: vertical; font: inherit; }
	.apply-form { display: grid; grid-template-columns: 9rem 1fr; gap: 0.5rem 0.7rem; align-items: center; margin-top: 0.5rem; }
	.apply-form label[for='apply-address'] { align-self: start; padding-top: 0.3rem; }
	.apply-form > div { grid-column: 2; }
	@media (max-width: 700px) {
		.apply-form { grid-template-columns: 1fr; }
		.apply-form > div { grid-column: 1; }
	}
</style>
