<script lang="ts">
	import { page } from '$app/state';
	import '../app.css';

	let { data, children } = $props();

	const links = [
		{ href: '/', label: 'Jobs' },
		{ href: '/attention', label: 'Needs you' },
		{ href: '/filters', label: 'Filters' },
		{ href: '/runs', label: 'Runs' },
		{ href: '/settings', label: 'Settings' }
	];

	function active(href: string) {
		const p = page.url.pathname;
		return href === '/' ? p === '/' || p.startsWith('/jobs') : p.startsWith(href);
	}

	function toggleTheme() {
		const root = document.documentElement;
		const dark = root.dataset.theme
			? root.dataset.theme === 'dark'
			: matchMedia('(prefers-color-scheme: dark)').matches;
		root.dataset.theme = dark ? 'light' : 'dark';
		try {
			localStorage.setItem('theme', root.dataset.theme);
		} catch {}
	}
</script>

<header>
	<nav>
		<a class="brand" href="/">🔎 JobHunter</a>
		{#each links as l}
			<a href={l.href} class:active={active(l.href)}>
				{l.label}
				{#if l.href === '/attention' && data.needsYou > 0}<span class="badge">{data.needsYou}</span>{/if}
			</a>
		{/each}
		<button class="ghost theme" onclick={toggleTheme} title="Toggle light/dark">◐</button>
	</nav>
</header>

<main>
	{@render children()}
</main>
