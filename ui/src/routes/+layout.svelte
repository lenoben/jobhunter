<script lang="ts">
	import { page } from '$app/state';
	import '../app.css';

	let { data, children } = $props();

	const links = [
		{ href: '/', label: 'Jobs' },
		{ href: '/attention', label: 'Needs you' },
		{ href: '/applications', label: 'Applications' },
		{ href: '/boards', label: 'Job boards' },
		{ href: '/filters', label: 'Filters' },
		{ href: '/runs', label: 'Runs' },
		{ href: '/stats', label: 'Statistics' },
		{ href: '/profile', label: 'Profile' },
		{ href: '/settings', label: 'Settings' }
	];

	function active(href: string) {
		const p = page.url.pathname;
		return href === '/' ? p === '/' || p.startsWith('/jobs') : p.startsWith(href);
	}

	// Phones: the menu is one sideways-scrolling row; keep the current page's link in view.
	let navEl: HTMLElement | undefined = $state();
	$effect(() => {
		page.url.pathname;
		const a = navEl?.querySelector<HTMLElement>('a.active');
		if (navEl && a && navEl.scrollWidth > navEl.clientWidth) {
			navEl.scrollLeft = a.offsetLeft - navEl.clientWidth / 2 + a.offsetWidth / 2;
		}
	});

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
	<nav bind:this={navEl}>
		<a class="brand" href="/">🔎 JobHunter</a>
		{#each links as l}
			<a href={l.href} class:active={active(l.href)}>
				{l.label}
				{#if l.href === '/attention' && data.needsYou > 0}<span class="badge">{data.needsYou}</span>{/if}
				{#if l.href === '/attention' && data.review > 0}<span class="badge review" title="Job-alert jobs to review">📥 {data.review}</span>{/if}
			</a>
		{/each}
		<button class="ghost theme" onclick={toggleTheme} title="Toggle light/dark">◐</button>
	</nav>
</header>

<main>
	{@render children()}
</main>
