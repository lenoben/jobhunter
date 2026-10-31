<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import { localTime } from '$lib/format';
	import { KINDS, TICKET_STATUS } from '$lib/tickets';
	import ConfirmDelete from '$lib/ConfirmDelete.svelte';

	let { data, form } = $props();
</script>

<svelte:head><title>Feedback · JobHunter</title></svelte:head>

<h1>Feedback</h1>
<p class="muted small intro">Found a problem, or have an idea? Write it here and send it to <strong>{data.to}</strong>.
	JobHunter never sends anything itself: it prepares the mail, and you send it from your own mailbox. Nothing is attached,
	so your profile, CV and logs stay on this PC.</p>

{#if form?.error}<div class="flash">{form.error}</div>{/if}
{#if form?.saved}<div class="flash">“{form.saved}” saved as a draft. Open it below whenever you want to finish or send it.</div>{/if}
{#if form?.deleted || page.url.searchParams.has('deleted')}<div class="flash">Draft deleted.</div>{/if}

<form class="card add" method="POST" action="?/save" use:enhance>
	<strong>+ New ticket</strong>
	<div class="row">
		<select name="kind" aria-label="Type" value={form?.values?.kind ?? 'issue'}>
			{#each Object.entries(KINDS) as [key, k]}<option value={key}>{k.emoji} {k.label}</option>{/each}
		</select>
		<input type="text" name="title" required maxlength="200" class="grow" placeholder="Short title" aria-label="Title" value={form?.values?.title ?? ''} />
	</div>
	<textarea name="body" rows="6" maxlength="20000" aria-label="Description" value={form?.values?.body ?? ''}
		placeholder="What happened, or what would you like? For a problem: what you did, what you expected, what you got instead."></textarea>
	<div>
		<label for="reply_to">Your email, if you'd like an answer (optional)</label>
		<input type="email" id="reply_to" name="reply_to" class="reply" value={form?.values?.reply_to ?? ''} />
	</div>
	<label class="check"><input type="checkbox" name="include_details" checked={!!form?.values?.include_details} />
		Add technical details (operating system, AI provider name, JobHunter version). You'll see them in the preview.</label>
	<div class="row">
		<button name="next" value="send">Continue to send →</button>
		<button class="secondary">Save for later</button>
	</div>
</form>

{#if data.tickets.length}
	<h2>Your tickets <span class="muted small">{data.tickets.length}</span></h2>
	<div class="table-wrap">
		<table class="stack">
			<thead><tr><th>Ticket</th><th class="hide-sm">Type</th><th>Status</th><th class="hide-sm">Last change</th><th></th></tr></thead>
			<tbody>
				{#each data.tickets as t (t.id)}
					<tr>
						<td class="fill"><a href="/feedback/{t.id}"><strong>{t.title}</strong></a>
							<div class="muted small">{t.ref}</div></td>
						<td class="hide-sm small">{KINDS[t.kind]?.emoji} {KINDS[t.kind]?.label ?? t.kind}</td>
						<td data-label="Status"><span class="pill">{TICKET_STATUS[t.status] ?? t.status}</span></td>
						<td class="hide-sm muted small">{localTime(t.updated_at)}</td>
						<td>{#if t.status === 'draft'}
							<ConfirmDelete action="?/delete" id={t.id} small title="Delete this draft" question="Delete this draft?" />
						{/if}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	.intro { max-width: 60rem; }
	.add { display: grid; gap: 0.6rem; }
	.reply { width: min(100%, 22rem); }
	.check { display: flex; gap: 0.4rem; align-items: baseline; margin: 0; }
</style>
