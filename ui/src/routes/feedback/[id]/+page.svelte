<script lang="ts">
	import { enhance } from '$app/forms';
	import { localTime } from '$lib/format';
	import { KINDS, TICKET_STATUS, ticketBody, ticketMailto, ticketSubject } from '$lib/tickets';
	import ConfirmDelete from '$lib/ConfirmDelete.svelte';
	import CopyButton from '$lib/CopyButton.svelte';

	let { data, form } = $props();
	const t = $derived(data.ticket);
	const isDraft = $derived(t.status === 'draft');

	// The form's current text, so the preview and the send buttons follow what is being typed.
	let kind = $state(data.ticket.kind);
	let title = $state(data.ticket.title);
	let body = $state(data.ticket.body);
	let replyTo = $state(data.ticket.reply_to ?? '');
	let includeDetails = $state(!!data.ticket.include_details);
	let busy = $state(false);

	const current = $derived({ ref: t.ref, kind, title, body, reply_to: replyTo });
	const subject = $derived(ticketSubject(current));
	const text = $derived(ticketBody(current, includeDetails ? data.info.details : null));
	const mailto = $derived(ticketMailto(data.info.to, subject, text));
	const ready = $derived(title.trim() !== '' && body.trim() !== '');

	const keepForm = () => {
		busy = true;
		return async ({ update }: { update: (o?: { reset?: boolean }) => Promise<void> }) => {
			await update({ reset: false });
			busy = false;
		};
	};
</script>

<svelte:head><title>{t.ref} · Feedback · JobHunter</title></svelte:head>

<p class="small"><a href="/feedback">← All tickets</a></p>
<h1>{t.title} <span class="pill">{TICKET_STATUS[t.status] ?? t.status}</span></h1>
<p class="muted small">{t.ref} · written {localTime(t.created_at)}{t.sent_at ? ` · sent ${localTime(t.sent_at)}` : ''}</p>

{#if form?.error}<div class="flash">{form.error}</div>{/if}
{#if form?.saved}<div class="flash">Saved.</div>{/if}
{#if form?.drafted}<div class="flash">Saved in your mailbox's “{form.drafted}” folder. Send it from there, then click <strong>Mark as sent</strong> here.</div>{/if}
{#if form?.moved === 'draft'}<div class="flash">Back to draft: you can edit, send or delete it again.</div>{/if}

{#if isDraft}
	<form method="POST" action="?/save" use:enhance={keepForm}>
		<div class="card fields">
			<div class="row">
				<select name="kind" aria-label="Type" bind:value={kind}>
					{#each Object.entries(KINDS) as [key, k]}<option value={key}>{k.emoji} {k.label}</option>{/each}
				</select>
				<input type="text" name="title" required maxlength="200" class="grow" aria-label="Title" bind:value={title} />
			</div>
			<textarea name="body" rows="8" maxlength="20000" aria-label="Description" bind:value={body}
				placeholder="What happened, or what would you like? For a problem: what you did, what you expected, what you got instead."></textarea>
			<div>
				<label for="reply_to">Your email, if you'd like an answer (optional)</label>
				<input type="email" id="reply_to" name="reply_to" class="reply" bind:value={replyTo} />
			</div>
			<label class="check"><input type="checkbox" name="include_details" bind:checked={includeDetails} />
				Add technical details (operating system, AI provider name, JobHunter version)</label>
			<div class="row">
				<button class="secondary" disabled={busy}>Save for later</button>
			</div>
		</div>

		<div class="card">
			<strong>Send it</strong>
			<p class="muted small">This is exactly what goes out. You send it yourself, then come back and click <strong>Mark as sent</strong>.</p>
			<pre class="preview">To: {data.info.to}
Subject: {subject}

{text}</pre>
			{#if !ready}
				<p class="muted small">Write a description to send this ticket.</p>
			{:else}
				<div class="row">
					{#if mailto}<a class="button" href={mailto}>✉ Open in my mail app</a>{/if}
					{#if data.info.drafts_available}
						<button class={mailto ? 'secondary' : ''} formaction="?/draft" disabled={busy}>Save as draft in my mailbox</button>
					{/if}
				</div>
				{#if !mailto}<p class="muted small">This text is too long for a mail-app link, which could cut it off. Copy it instead.</p>{/if}
				<p class="muted small">Nothing opens, or you use webmail? Copy the parts into a new mail:</p>
				<div class="row">
					<CopyButton text={data.info.to} label="Copy address" />
					<CopyButton text={subject} label="Copy subject" />
					<CopyButton {text} label="Copy text" />
				</div>
				<div class="row sent-row">
					<button formaction="?/sent" disabled={busy}>✓ Mark as sent</button>
				</div>
			{/if}
		</div>
	</form>
	<ConfirmDelete action="?/delete" title="Delete this draft" question="Delete this draft for good?" />
{:else}
	<div class="card">
		<pre class="preview">To: {data.info.to}
Subject: {ticketSubject(t)}

{ticketBody(t, t.include_details ? data.info.details : null)}</pre>
		<div class="row">
			{#if t.status === 'sent'}
				<form method="POST" action="?/resolve" use:enhance><button class="secondary">Mark as resolved</button></form>
				<form method="POST" action="?/unsend" use:enhance><button class="ghost">Not sent after all</button></form>
			{:else}
				<form method="POST" action="?/reopen" use:enhance><button class="secondary">Reopen</button></form>
			{/if}
		</div>
	</div>
{/if}

<style>
	.fields { display: grid; gap: 0.6rem; }
	.reply { width: min(100%, 22rem); }
	.check { display: flex; gap: 0.4rem; align-items: baseline; margin: 0; }
	.preview { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--surface-2); border-radius: var(--radius); padding: 0.7rem 0.9rem; font-size: 0.85rem; }
	.sent-row { margin-top: 0.8rem; }
</style>
