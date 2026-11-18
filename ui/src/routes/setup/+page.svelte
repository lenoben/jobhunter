<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();
	const s = $derived(data.s);
	// svelte-ignore state_referenced_locally
	let provider = $state(data.s.llm.suggested); // the saved one, or Gemini on a fresh PC without Claude Code
	let starter = $state(true);
	let busy = $state('');

	// Python needs a few seconds (it logs in to the mailbox, asks Telegram): show that it is working.
	const saving = (step: string) => () => {
		busy = step;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = '';
		};
	};
	const mine = (step: string) => (form?.step === step ? form : null);
	const models = $derived((mine('llm') as any)?.models ?? []);
	const telegram = $derived(mine('telegram') as any);
	// Gemini (free tier) first: most people start there (user decision 2026-11-16).
	const LABELS: Record<string, string> = {
		gemini: 'Google Gemini — free tier, recommended to start',
		'claude-code': 'Claude Code — needs a Claude subscription, best documents',
		groq: 'Groq — free tier', openai: 'OpenAI', openrouter: 'OpenRouter', mistral: 'Mistral',
		ollama: 'Ollama — a model on this PC', custom: 'Other OpenAI-compatible API'
	};
	const providers = $derived(['gemini', ...data.s.llm.providers.filter((p: string) => p !== 'gemini')]);
	// First pick: the saved model, else Python's suggestion (agent.suggest_models: free-tier friendly).
	const pick = (key: string) => s.llm[key] || (mine('llm') as any)?.suggested?.[key] || models[0];
</script>

<svelte:head><title>Setup · JobHunter</title></svelte:head>

<h1>Setup</h1>
<p class="muted small intro">Each step saves on its own, so you can stop and come back. Passwords and keys are stored only in
	the file <code>.env</code> on this PC and are never shown again: an empty password field keeps the one already saved.</p>

{#if s.done}
	<div class="flash">✓ The required steps are done. Next: <a href="/profile">fill in your profile</a>, the only source of
		facts for your CVs. Then start a run on the <a href="/settings">Settings</a> page.</div>
{/if}

{#snippet head(n: number, title: string, done: boolean, optional = false)}
	<div class="row head">
		<strong>{n}. {title}</strong>
		{#if done}<span class="pill ok">✓ done</span>{:else if optional}<span class="pill">optional</span>{:else}<span class="pill todo">to do</span>{/if}
	</div>
{/snippet}

{#snippet result(step: string, okText: string)}
	{@const r = mine(step) as any}
	{#if r?.error}<div class="flash">{r.error}</div>{/if}
	{#if r?.warning}<div class="flash">{r.warning}</div>{/if}
	{#if r?.ok && !r.pending && !r.need_models}<div class="saved">✓ {okText}</div>{/if}
{/snippet}

{#snippet save(step: string, label = 'Save')}
	<div><button disabled={busy !== ''}>{busy === step ? 'Working…' : label}</button></div>
{/snippet}

<form class="card" method="POST" use:enhance={saving('llm')}>
	<input type="hidden" name="step" value="llm" />
	{@render head(1, 'AI that searches and writes', s.llm.done)}
	<p class="muted small">No subscription? Start with <strong>Google Gemini</strong>: its API key is free (a Google account is
		enough). Claude Code needs a Claude subscription and writes the best documents.</p>
	{@render result('llm', 'Saved.')}
	<div>
		<label for="provider">Provider</label>
		<select id="provider" name="provider" bind:value={provider}>
			{#each providers as p}<option value={p}>{LABELS[p] ?? p}</option>{/each}
		</select>
	</div>
	{#if provider === 'claude-code'}
		{#if !s.llm.claude_installed}
			<div class="flash">Claude Code is not installed on this PC. Install it from
				<a href="https://claude.com/claude-code" target="_blank" rel="noopener noreferrer">claude.com/claude-code</a>,
				run <code>claude</code> once to log in, then reload this page. Or pick another provider.</div>
		{/if}
		<div class="row">
			<div><label for="model_filter">Model for searching and scoring</label>
				<select id="model_filter" name="model_filter" value={s.llm.model_filter}>
					{#each s.llm.claude_models as m}<option value={m}>{m}</option>{/each}
				</select></div>
			<div><label for="model_writer">Model for CVs and letters</label>
				<select id="model_writer" name="model_writer" value={s.llm.model_writer}>
					{#each s.llm.claude_models as m}<option value={m}>{m}</option>{/each}
				</select></div>
		</div>
	{:else}
		{#if provider === 'custom'}
			<div><label for="base_url">API base URL (OpenAI-compatible, ends in /v1)</label>
				<input type="url" id="base_url" name="base_url" class="wide" value={s.llm.base_url} /></div>
		{/if}
		{#if provider !== 'ollama'}
			<div><label for="api_key">API key
					{#if s.llm.key_urls[provider]}— create one at <a href={s.llm.key_urls[provider]} target="_blank" rel="noopener noreferrer">{s.llm.key_urls[provider]}</a>{/if}</label>
				<input type="password" id="api_key" name="api_key" class="wide" autocomplete="off"
					placeholder={s.llm.key_set && provider === s.llm.provider ? 'saved — leave empty to keep it' : 'paste the key'} />
				{#if provider === 'gemini'}<p class="muted small" style="margin: 0.3rem 0 0">A free key is enough. JobHunter
					suggests the Flash models, which have the most free requests per day; you can change them here or in
					Settings at any time.</p>{/if}</div>
		{/if}
		{#if (mine('llm') as any)?.need_models}
			<div class="flash">Key saved. Now pick a fast, cheap model for searching and a strong one for writing, then save again.</div>
		{/if}
		<div class="row">
			{#each [['llm_model_filter', 'Model for searching and scoring'], ['llm_model_writer', 'Model for CVs and letters']] as [key, label]}
				<div class="grow"><label for={key}>{label}</label>
					{#if models.length}
						<select id={key} name={key} value={pick(key)}>
							{#each models as m}<option value={m}>{m}</option>{/each}
						</select>
					{:else}
						<input type="text" id={key} name={key} class="wide" value={provider === s.llm.provider ? s.llm[key] : ''}
							placeholder="Save once to load the provider's model list" />
					{/if}</div>
			{/each}
		</div>
	{/if}
	{@render save('llm')}
</form>

<form class="card" method="POST" use:enhance={saving('countries')}>
	<input type="hidden" name="step" value="countries" />
	{@render head(2, 'Where do you want to work?', s.countries.keys.length > 0)}
	{@render result('countries', 'Saved.')}
	<div><label for="countries">Countries, comma-separated. Also <code>remote</code> (remote jobs in any country) and <code>worldwide</code>.</label>
		<input type="text" id="countries" name="countries" class="wide" value={s.countries.keys.join(', ')} />
		<div class="muted small">For example: {s.countries.common.slice(0, 8).map((c: any) => c.label).join(', ')}.
			Each search filter can use its own list later.</div></div>
	<div><label for="himalayas_key">Himalayas API key for the remote-jobs board (optional, free at himalayas.app/api)</label>
		<input type="password" id="himalayas_key" name="himalayas_key" class="wide" autocomplete="off"
			placeholder={s.countries.himalayas_set ? 'saved — leave empty to keep it' : 'not needed'} /></div>
	{@render save('countries')}
</form>

<form class="card" method="POST" use:enhance={saving('mail')}>
	<input type="hidden" name="step" value="mail" />
	{@render head(3, 'Email', !!s.mail.send.address || !!s.mail.alerts.address, true)}
	<p class="muted small">JobHunter never sends email. With a mailbox it saves application emails as <strong>drafts</strong> with your
		PDFs attached, and can read your LinkedIn / Instaffo job-alert emails (read-only). Use an <strong>app password</strong> from
		your mail provider's security settings, never your normal password. Saving logs in once to check it.</p>
	{@render result('mail', 'Saved, and the login worked.')}
	{#each [['send', 'Drafts mailbox', 'Leave the address empty for no drafts.'], ['alerts', 'Job-alert mailbox', 'Leave the address empty to read alerts from the drafts mailbox.']] as [key, title, hint]}
		{@const m = s.mail[key]}
		<fieldset>
			<legend>{title}</legend>
			<div class="row">
				<div class="grow"><label for="{key}_address">Email address</label>
					<input type="email" id="{key}_address" name="{key}_address" class="wide" value={m.address} /></div>
				<div class="grow"><label for="{key}_password">App password</label>
					<input type="password" id="{key}_password" name="{key}_password" class="wide" autocomplete="off"
						placeholder={m.password_set ? 'saved — leave empty to keep it' : ''} /></div>
			</div>
			<div><label for="{key}_host">IMAP host — only for providers other than Yahoo, Gmail, GMX, web.de, T-Online and iCloud</label>
				<input type="text" id="{key}_host" name="{key}_host" class="wide" value={m.host} placeholder="e.g. imap.example.com" /></div>
			<div class="muted small">{hint}</div>
		</fieldset>
	{/each}
	{@render save('mail')}
</form>

<form class="card" method="POST" use:enhance={saving('telegram')}>
	<input type="hidden" name="step" value="telegram" />
	{@render head(4, 'Telegram', s.telegram.done)}
	<p class="muted small">Required: run summaries, jobs that need you and failed runs arrive there.</p>
	{@render result('telegram', 'A test message was sent. Check Telegram.')}
	<ol class="muted small">
		<li>In Telegram, open <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer">@BotFather</a> and send <code>/newbot</code>.</li>
		<li>Choose a name and a username ending in “bot”.</li>
		<li>Copy the token BotFather sends (it looks like <code>123456:ABC…</code>) and paste it here.</li>
	</ol>
	<div><label for="token">Bot token</label>
		<input type="password" id="token" name="token" class="wide" autocomplete="off"
			placeholder={s.telegram.token_set ? 'saved — leave empty to keep it' : 'paste the token'} /></div>
	{#if telegram?.pending}
		<div class="flash">
			{#if telegram.chats.length}
				Several chats wrote to the bot. Pick yours:
				<select name="chat" aria-label="Chat">{#each telegram.chats as c}<option value={c.id}>{c.label}</option>{/each}</select>
			{:else}
				The token works. Now open <a href="https://t.me/{telegram.bot}" target="_blank" rel="noopener noreferrer">t.me/{telegram.bot}</a>
				in Telegram, press <strong>Start</strong> or send any message, then click the button below again.
			{/if}
		</div>
	{/if}
	{@render save('telegram', s.telegram.done && !telegram?.pending ? 'Send a test message' : telegram?.pending ? 'I sent the message — connect' : 'Check the token')}
</form>

<form class="card" method="POST" use:enhance={saving('permit')}>
	<input type="hidden" name="step" value="permit" />
	{@render head(5, 'Work permit', true)}
	{@render result('permit', 'Saved.')}
	<p class="muted small">If you need a work permit or visa sponsorship where you apply, jobs that rule it out (“no visa sponsorship”,
		“US citizens only”) are flagged for you to decide. With Germany as a target, jobs below the EU Blue Card salary are flagged too.</p>
	<label class="check"><input type="radio" name="need" value="yes" checked={s.permit} /> I need a work permit or sponsorship</label>
	<label class="check"><input type="radio" name="need" value="no" checked={!s.permit} /> I don't (for example, I'm a citizen)</label>
	{@render save('permit')}
</form>

<form class="card" method="POST" use:enhance={saving('filters')}>
	<input type="hidden" name="step" value="filters" />
	{@render head(6, 'What jobs to search for', s.filters.count > 0)}
	{@render result('filters', 'Search filters created.')}
	{#if s.filters.count}
		<p>You have {s.filters.count} search filter{s.filters.count === 1 ? '' : 's'}. Edit them on the <a href="/filters">Filters</a> page.</p>
	{:else}
		<label class="check"><input type="radio" name="starter" value="yes" checked={starter} onchange={() => (starter = true)} />
			The IT starter set: {s.filters.starter.join('; ')}</label>
		<label class="check"><input type="radio" name="starter" value="no" checked={!starter} onchange={() => (starter = false)} />
			My own job titles (any field)</label>
		{#if !starter}
			<label for="lines">One filter per line as <code>Name: job title, job title</code>. Titles in every language of your countries help.</label>
			<textarea id="lines" name="lines" rows="4" placeholder="Nursing: Registered Nurse, Pflegefachkraft"></textarea>
		{/if}
		{@render save('filters', 'Create filters')}
	{/if}
</form>

<style>
	.intro { max-width: 60rem; }
	form.card { display: flex; flex-direction: column; gap: 0.7rem; }
	form.card p, form.card ol { margin: 0; }
	.head { justify-content: space-between; }
	.pill.ok { color: var(--good, #1a7f37); }
	.pill.todo { color: var(--warn); }
	.saved { color: var(--good, #1a7f37); font-weight: 600; }
	.wide { width: 100%; }
	input[type='password'] { padding: 0.35rem 0.55rem; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
	fieldset { border: 1px solid var(--border); border-radius: var(--radius); padding: 0.6rem 0.8rem; display: flex; flex-direction: column; gap: 0.5rem; }
	legend { font-weight: 600; font-size: 0.9rem; padding: 0 0.3rem; }
	label.check { display: flex; gap: 0.45rem; align-items: baseline; color: var(--text); font-size: 0.95rem; }
</style>
