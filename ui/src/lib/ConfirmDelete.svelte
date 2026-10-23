<script lang="ts">
	// Two-step delete (user request 2026-10-25): the first click only asks; "Yes, delete" submits with
	// confirm=yes, which the server action requires. No browser dialog, so it works the same on phones.
	import { enhance } from '$app/forms';

	let { action, id = null, question, small = false }: {
		action: string; id?: number | null; question: string; small?: boolean;
	} = $props();
	let asking = $state(false);
</script>

{#if asking}
	<form method="POST" {action} use:enhance class="row confirm-delete" style="gap: 0.3rem; flex-wrap: wrap; align-items: center">
		{#if id !== null}<input type="hidden" name="id" value={id} />{/if}
		<input type="hidden" name="confirm" value="yes" />
		<span class="small">{question}</span>
		<button class="danger" class:small>Yes, delete</button>
		<button type="button" class="secondary" class:small onclick={() => (asking = false)}>Cancel</button>
	</form>
{:else}
	<button type="button" class="ghost" class:small title="Delete this job and its documents" onclick={() => (asking = true)}>🗑{small ? '' : ' Delete'}</button>
{/if}
