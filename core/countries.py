"""Target countries (user request 2026-10-25): where the user looks for jobs.

The setting `search_countries` (JSON list, set by `cli.py setup`) is the default for every filter;
a filter's own `countries` (non-empty) replaces it. Keys are python-jobspy's country names, plus
two special targets:
* `remote`: remote jobs not tied to one country (Himalayas, Jobicy, LinkedIn "Worldwide" remote);
* `worldwide`: any location, including on-site jobs abroad.
Each source says which targets it covers (`countries` on the adapter, None = all; core §16).
"""

from __future__ import annotations

import json

REMOTE, WORLDWIDE = "remote", "worldwide"
SPECIAL = {REMOTE: "Remote (any country)", WORLDWIDE: "Worldwide (incl. on-site abroad)"}

# key (= jobspy country name) → (label, ISO 3166 alpha-2)
COUNTRIES: dict[str, tuple[str, str]] = {
    "argentina": ("Argentina", "AR"), "australia": ("Australia", "AU"), "austria": ("Austria", "AT"),
    "bahrain": ("Bahrain", "BH"), "bangladesh": ("Bangladesh", "BD"), "belgium": ("Belgium", "BE"),
    "bulgaria": ("Bulgaria", "BG"), "brazil": ("Brazil", "BR"), "canada": ("Canada", "CA"),
    "chile": ("Chile", "CL"), "china": ("China", "CN"), "colombia": ("Colombia", "CO"),
    "costa rica": ("Costa Rica", "CR"), "croatia": ("Croatia", "HR"), "cyprus": ("Cyprus", "CY"),
    "czech republic": ("Czech Republic", "CZ"), "denmark": ("Denmark", "DK"), "ecuador": ("Ecuador", "EC"),
    "egypt": ("Egypt", "EG"), "estonia": ("Estonia", "EE"), "finland": ("Finland", "FI"),
    "france": ("France", "FR"), "germany": ("Germany", "DE"), "greece": ("Greece", "GR"),
    "hong kong": ("Hong Kong", "HK"), "hungary": ("Hungary", "HU"), "india": ("India", "IN"),
    "indonesia": ("Indonesia", "ID"), "ireland": ("Ireland", "IE"), "israel": ("Israel", "IL"),
    "italy": ("Italy", "IT"), "japan": ("Japan", "JP"), "kuwait": ("Kuwait", "KW"),
    "latvia": ("Latvia", "LV"), "lithuania": ("Lithuania", "LT"), "luxembourg": ("Luxembourg", "LU"),
    "malaysia": ("Malaysia", "MY"), "malta": ("Malta", "MT"), "mexico": ("Mexico", "MX"),
    "morocco": ("Morocco", "MA"), "netherlands": ("Netherlands", "NL"), "new zealand": ("New Zealand", "NZ"),
    "nigeria": ("Nigeria", "NG"), "norway": ("Norway", "NO"), "oman": ("Oman", "OM"),
    "pakistan": ("Pakistan", "PK"), "panama": ("Panama", "PA"), "peru": ("Peru", "PE"),
    "philippines": ("Philippines", "PH"), "poland": ("Poland", "PL"), "portugal": ("Portugal", "PT"),
    "qatar": ("Qatar", "QA"), "romania": ("Romania", "RO"), "saudi arabia": ("Saudi Arabia", "SA"),
    "singapore": ("Singapore", "SG"), "slovakia": ("Slovakia", "SK"), "slovenia": ("Slovenia", "SI"),
    "south africa": ("South Africa", "ZA"), "south korea": ("South Korea", "KR"), "spain": ("Spain", "ES"),
    "sweden": ("Sweden", "SE"), "switzerland": ("Switzerland", "CH"), "taiwan": ("Taiwan", "TW"),
    "thailand": ("Thailand", "TH"), "turkey": ("Turkey", "TR"), "ukraine": ("Ukraine", "UA"),
    "united arab emirates": ("United Arab Emirates", "AE"), "uk": ("United Kingdom", "GB"),
    "usa": ("USA", "US"), "uruguay": ("Uruguay", "UY"), "venezuela": ("Venezuela", "VE"),
    "vietnam": ("Vietnam", "VN"),
}
ALIASES = {"us": "usa", "united states": "usa", "america": "usa", "united kingdom": "uk", "gb": "uk",
           "great britain": "uk", "england": "uk", "deutschland": "germany", "de": "germany",
           "uae": "united arab emirates", "czechia": "czech republic", "türkiye": "turkey",
           "anywhere": REMOTE, "global": WORLDWIDE}
# shown as a numbered menu in cli.py setup; any other key can be typed by name
COMMON = ["germany", "usa", "uk", "canada", "ireland", "netherlands", "australia", "india",
          "nigeria", "south africa", REMOTE, WORLDWIDE]
DEFAULT = ["germany"]


def label(key: str) -> str:
    return SPECIAL.get(key) or COUNTRIES.get(key, (key, ""))[0]


def normalize(name: str) -> str | None:
    """'United States' / 'US' / 'usa' → 'usa'; None if unknown."""
    k = " ".join(name.strip().casefold().split())
    k = ALIASES.get(k, k)
    return k if k in COUNTRIES or k in SPECIAL else None


def parse(text: str) -> tuple[list[str], list[str]]:
    """'usa, UK, remote' → (['usa', 'uk', 'remote'], unknown names). Order kept, duplicates dropped."""
    keys, unknown = [], []
    for part in text.replace(";", ",").split(","):
        if not part.strip():
            continue
        k = normalize(part)
        if k is None:
            unknown.append(part.strip())
        elif k not in keys:
            keys.append(k)
    return keys, unknown


def from_setting(value: str | None) -> list[str]:
    try:
        keys = [k for k in json.loads(value or "[]") if normalize(k)]
    except (ValueError, TypeError):
        keys = []
    return [normalize(k) for k in keys] or list(DEFAULT)


def effective(filter_countries: list[str] | None, settings: dict[str, str]) -> list[str]:
    """A filter's own countries, else the global setting search_countries (default Germany)."""
    own = [k for k in (normalize(c) for c in filter_countries or []) if k]
    return own or from_setting(settings.get("search_countries"))


def iso2(key: str) -> str | None:
    return COUNTRIES.get(key, (None, None))[1]


_EUROPE = {"austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic", "denmark", "estonia",
           "finland", "france", "germany", "greece", "hungary", "ireland", "italy", "latvia", "lithuania",
           "luxembourg", "malta", "netherlands", "norway", "poland", "portugal", "romania", "slovakia",
           "slovenia", "spain", "sweden", "switzerland", "uk", "ukraine"}
_MIDDLE_EAST = {"bahrain", "israel", "kuwait", "oman", "qatar", "saudi arabia", "turkey", "united arab emirates"}
_AFRICA = {"egypt", "morocco", "nigeria", "south africa"}
_LATAM = {"argentina", "brazil", "chile", "colombia", "costa rica", "ecuador", "mexico", "panama", "peru",
          "uruguay", "venezuela"}
_APAC = {"australia", "bangladesh", "china", "hong kong", "india", "indonesia", "japan", "malaysia",
         "new zealand", "pakistan", "philippines", "singapore", "south korea", "taiwan", "thailand", "vietnam"}
# region names used by remote boards (Jobicy jobGeo) → the countries they include
REGIONS = {"europe": _EUROPE, "eu": _EUROPE - {"uk", "norway", "switzerland", "ukraine"},
           "emea": _EUROPE | _MIDDLE_EAST | _AFRICA, "africa": _AFRICA, "middle east": _MIDDLE_EAST,
           "latam": _LATAM, "apac": _APAC, "asia": _APAC, "north america": {"usa", "canada", "mexico"},
           "americas": {"usa", "canada"} | _LATAM}
_ANYWHERE = {"anywhere", "worldwide", "global", "remote", ""}


def geo_matches(geo: str | None, targets: list[str]) -> bool:
    """Does a remote job's allowed-location text ('Canada, USA', 'EMEA', 'Anywhere') fit the targets?
    'Anywhere' fits every target; a country or region fits the countries in it; 'remote' and
    'worldwide' accept every location."""
    if REMOTE in targets or WORLDWIDE in targets:
        return True
    want = set(targets)
    for part in (geo or "").replace(";", ",").replace("/", ",").split(","):
        p = " ".join(part.strip().casefold().split())
        if p in _ANYWHERE or normalize(p) in want or want & REGIONS.get(p, set()):
            return True
    return False
