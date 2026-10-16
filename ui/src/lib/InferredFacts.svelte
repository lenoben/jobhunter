<script lang="ts">
	// R5/R9: statements implied by (not written in) the profile, waiting for the user's decision.
	import { enhance } from '$app/forms';

	let { facts, action = '' }: { facts: any[]; action?: string } = $props();
</script>

<div class="table-wrap">
	<table>
		<thead><tr><th>Document</th><th>Where</th><th>Statement</th><th>Basis in your profile</th></tr></thead>
		<tbody>
			{#each facts as f}
				<tr><td>{f.document}</td><td class="muted small">{f.where || '–'}</td><td>{f.text}</td><td class="small">{f.basis}</td></tr>
			{/each}
		</tbody>
	</table>
</div>
<div class="row" style="margin-top: 0.7rem">
	<form method="POST" action="{action}?/approve" use:enhance>
		<button>Approve → docs ready</button>
	</form>
	<form method="POST" action="{action}?/reject" use:enhance class="row grow">
		<input type="text" name="note" placeholder="Optional: what is wrong" class="grow" />
		<button class="danger">Reject → re-render without them</button>
	</form>
</div>
