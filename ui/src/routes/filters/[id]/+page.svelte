<script lang="ts">
	import { label } from '$lib/format';

	let { data, form } = $props();
	const f = $derived(form?.filter ?? data.filter);
	const o = $derived(data.options);
</script>

<svelte:head><title>{f.id ? f.name : 'New filter'} · JobHunter</title></svelte:head>

<p class="small"><a href="/filters">← Filters</a></p>
<h1>{f.id ? `Edit: ${f.name}` : 'New filter'}</h1>

{#if form?.errors}
	<div class="flash">{#each form.errors as e}<div>{e}</div>{/each}</div>
{/if}

<form method="POST" action="?/save" class="card" style="display: grid; gap: 0.9rem">
	<div class="row">
		<div class="grow">
			<label for="name">Name</label>
			<input id="name" type="text" name="name" value={f.name} required style="width: 100%" />
		</div>
		<div class="checks" style="padding-top: 1.2rem">
			<label><input type="checkbox" name="active" checked={f.active} /> Active</label>
		</div>
	</div>

	<div>
		<label for="keywords">Keywords (comma or one per line; any of them matches)</label>
		<textarea id="keywords" name="keywords">{f.keywords.join(', ')}</textarea>
	</div>
	<div>
		<label for="exclude_keywords">Exclude keywords (in the job title)</label>
		<textarea id="exclude_keywords" name="exclude_keywords" style="min-height: 2.6rem">{f.exclude_keywords.join(', ')}</textarea>
	</div>

	<div>
		<label for="countries">Countries (empty = your default: {data.defaultCountries})</label>
		<input id="countries" type="text" name="countries" value={(f.countries ?? []).join(', ')} placeholder="e.g. usa, uk, remote" style="width: 100%" />
		<p class="muted small" style="margin: 0.2rem 0 0">Comma-separated: country names, <code>remote</code> (remote jobs in any country) or <code>worldwide</code>. Sources that don't cover them are skipped: Bundesagentur and Arbeitnow are Germany only; Himalayas and Jobicy are remote jobs only.</p>
	</div>

	<div class="row">
		<div class="grow">
			<label for="location">City (empty = anywhere in the countries; best with one country)</label>
			<input id="location" type="text" name="location" value={f.location ?? ''} style="width: 100%" />
		</div>
		<div>
			<label for="radius_km">Radius km</label>
			<input id="radius_km" type="number" name="radius_km" min="0" max="500" value={f.radius_km} style="width: 6rem" />
		</div>
		<div>
			<label for="max_age_days">Max. age (days)</label>
			<input id="max_age_days" type="number" name="max_age_days" min="1" max="100" value={f.max_age_days} style="width: 6rem" />
		</div>
		<div>
			<label for="min_fit_score">Min. fit score</label>
			<input id="min_fit_score" type="number" name="min_fit_score" min="0" max="100" value={f.min_fit_score} style="width: 6rem" />
		</div>
	</div>

	<fieldset>
		<legend>Work modes</legend>
		<div class="checks">
			{#each o.WORK_MODES as v}<label><input type="checkbox" name="work_modes" value={v} checked={f.work_modes.includes(v)} /> {v}</label>{/each}
		</div>
	</fieldset>
	<fieldset>
		<legend>Employment types</legend>
		<div class="checks">
			{#each o.EMPLOYMENT_TYPES as v}<label><input type="checkbox" name="employment_types" value={v} checked={f.employment_types.includes(v)} /> {label(v)}</label>{/each}
			<label><input type="checkbox" name="exclude_freelance" checked={f.exclude_freelance} /> <strong>exclude freelance</strong></label>
		</div>
	</fieldset>
	<div class="row" style="align-items: stretch">
		<fieldset class="grow">
			<legend>Posting languages</legend>
			<div class="checks">
				{#each o.LANGUAGES as v}<label><input type="checkbox" name="languages" value={v} checked={f.languages.includes(v)} /> {v}</label>{/each}
			</div>
		</fieldset>
		<fieldset class="grow">
			<legend>Sources</legend>
			<div class="checks">
				{#each o.SOURCES as v}<label><input type="checkbox" name="sources" value={v} checked={f.sources.includes(v)} /> {v}</label>{/each}
			</div>
		</fieldset>
	</div>

	<div class="row">
		<button>Save filter</button>
		<a class="button secondary" href="/filters">Cancel</a>
	</div>
</form>
