// Target countries — mirrors core/countries.py (keys = python-jobspy country names + remote/worldwide).

export const SPECIAL: Record<string, string> = { remote: 'Remote (any country)', worldwide: 'Worldwide (incl. on-site abroad)' };

export const COUNTRIES: Record<string, string> = {
	argentina: 'Argentina', australia: 'Australia', austria: 'Austria', bahrain: 'Bahrain', bangladesh: 'Bangladesh',
	belgium: 'Belgium', bulgaria: 'Bulgaria', brazil: 'Brazil', canada: 'Canada', chile: 'Chile', china: 'China',
	colombia: 'Colombia', 'costa rica': 'Costa Rica', croatia: 'Croatia', cyprus: 'Cyprus', 'czech republic': 'Czech Republic',
	denmark: 'Denmark', ecuador: 'Ecuador', egypt: 'Egypt', estonia: 'Estonia', finland: 'Finland', france: 'France',
	germany: 'Germany', greece: 'Greece', 'hong kong': 'Hong Kong', hungary: 'Hungary', india: 'India',
	indonesia: 'Indonesia', ireland: 'Ireland', israel: 'Israel', italy: 'Italy', japan: 'Japan', kuwait: 'Kuwait',
	latvia: 'Latvia', lithuania: 'Lithuania', luxembourg: 'Luxembourg', malaysia: 'Malaysia', malta: 'Malta',
	mexico: 'Mexico', morocco: 'Morocco', netherlands: 'Netherlands', 'new zealand': 'New Zealand', nigeria: 'Nigeria',
	norway: 'Norway', oman: 'Oman', pakistan: 'Pakistan', panama: 'Panama', peru: 'Peru', philippines: 'Philippines',
	poland: 'Poland', portugal: 'Portugal', qatar: 'Qatar', romania: 'Romania', 'saudi arabia': 'Saudi Arabia',
	singapore: 'Singapore', slovakia: 'Slovakia', slovenia: 'Slovenia', 'south africa': 'South Africa',
	'south korea': 'South Korea', spain: 'Spain', sweden: 'Sweden', switzerland: 'Switzerland', taiwan: 'Taiwan',
	thailand: 'Thailand', turkey: 'Turkey', ukraine: 'Ukraine', 'united arab emirates': 'United Arab Emirates',
	uk: 'United Kingdom', usa: 'USA', uruguay: 'Uruguay', venezuela: 'Venezuela', vietnam: 'Vietnam'
};

const ALIASES: Record<string, string> = {
	us: 'usa', 'united states': 'usa', america: 'usa', 'united kingdom': 'uk', gb: 'uk', 'great britain': 'uk',
	england: 'uk', deutschland: 'germany', de: 'germany', uae: 'united arab emirates', czechia: 'czech republic',
	türkiye: 'turkey', anywhere: 'remote', global: 'worldwide'
};

export function countryLabel(key: string): string {
	return SPECIAL[key] ?? COUNTRIES[key] ?? key;
}

/** "USA, uk; Remote" → { keys: ['usa', 'uk', 'remote'], unknown: [] } (order kept, no duplicates). */
export function parseCountries(text: string): { keys: string[]; unknown: string[] } {
	const keys: string[] = [];
	const unknown: string[] = [];
	for (const part of text.split(/[,;\n]/)) {
		const raw = part.trim();
		if (!raw) continue;
		let k = raw.toLowerCase().split(/\s+/).join(' ');
		k = ALIASES[k] ?? k;
		if (!(k in COUNTRIES) && !(k in SPECIAL)) unknown.push(raw);
		else if (!keys.includes(k)) keys.push(k);
	}
	return { keys, unknown };
}

export function parseCountryList(json: string | null | undefined): string[] {
	try {
		const v = JSON.parse(json || '[]');
		return Array.isArray(v) ? v.map(String) : [];
	} catch {
		return [];
	}
}
