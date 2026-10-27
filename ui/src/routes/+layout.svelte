<script lang="ts">
	import { page } from '$app/state';
	import '../app.css';

	let { data, children } = $props();

	// The project's author (shown in the header and footer of every page; this is the project's own
	// credit, the same for everyone who uses it, not the user's profile).
	const AUTHOR = 'lenoben';
	const AUTHOR_URL = 'https://www.lenoben.top';
	const REPO_URL = 'https://github.com/lenoben/jobhunt';

	const links = [
		{ href: '/', label: 'Jobs' },
		{ href: '/attention', label: 'Needs you' },
		{ href: '/applications', label: 'Applications' },
		{ href: '/boards', label: 'Job boards' },
		{ href: '/recruiters', label: 'Recruiters' },
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
		<span class="brand-wrap">
			<a class="brand" href="/">🔎 JobHunter</a>
			<a class="byline" href={AUTHOR_URL} target="_blank" rel="noopener noreferrer" title="Built by {AUTHOR}">by {AUTHOR}</a>
		</span>
		{#each links as l}
			<a href={l.href} class:active={active(l.href)}>
				{l.label}
				{#if l.href === '/attention' && data.needsYou > 0}<span class="badge">{data.needsYou}</span>{/if}
				{#if l.href === '/attention' && data.review > 0}<span class="badge review" title="Job-alert jobs to review">📥 {data.review}</span>{/if}
				{#if l.href === '/recruiters' && data.recruiters > 0}<span class="badge recruiter" title="New jobs via a recruiter: documents only on request">🤝 {data.recruiters}</span>{/if}
			</a>
		{/each}
		<button class="ghost theme" onclick={toggleTheme} title="Toggle light/dark">◐</button>
	</nav>
</header>

<main>
	{@render children()}
</main>

<footer class="site-footer">
	<div class="footer-inner">
		<span class="footer-brand">🔎 JobHunter</span>
		<span class="footer-sep" aria-hidden="true"></span>
		<span>Built by <a href={AUTHOR_URL} target="_blank" rel="noopener noreferrer">{AUTHOR}</a></span>
		<span class="footer-dot" aria-hidden="true">·</span>
		<a href={AUTHOR_URL} target="_blank" rel="noopener noreferrer">{AUTHOR_URL.replace(/^https?:\/\/(www\.)?/, '')}</a>
		<span class="footer-dot" aria-hidden="true">·</span>
		<a href={REPO_URL} target="_blank" rel="noopener noreferrer">Source on GitHub</a>
		<span class="grow"></span>
		<span class="muted">Runs on your computer. You always submit your applications yourself.</span>
	</div>
</footer>
