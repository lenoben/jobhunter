"""Deterministic screening checks (CLAUDE.md §5a). Run on every newly found job during search."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SalaryResult:
    annual_eur: float | None
    flag: str                 # ok | below_blue_card_threshold | salary_unknown


# --- Salary vs. EU Blue Card -----------------------------------------------------------------

_NUM_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[.,   ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s*(k(?![a-zä])|tsd\.?|tausend|t€)?",
    re.IGNORECASE,
)
_HOURLY_RE = re.compile(r"stunde|\bstd\b|/\s*h\b|per\s+hour|\bhourly\b|stündlich|\bhour\b", re.I)
_MONTHLY_RE = re.compile(r"monat|\bmtl\b|/\s*mo\b|per\s+month|\bmonthly\b|\bmonth\b|p\.\s*m\.", re.I)
_YEARLY_RE = re.compile(r"jahr|jährlich|p\.\s*a\.|/\s*a\b|per\s+(?:year|annum)|\byearly\b|\bannual|\byear\b", re.I)
_NON_EUR_RE = re.compile(r"\$|\busd\b|£|\bgbp\b|\bchf\b|\bpln\b", re.I)
HOURS_PER_YEAR = 40 * 52


def _to_float(raw: str) -> float:
    s = raw.replace(" ", " ").replace(" ", " ")
    m = re.fullmatch(r"(\d{1,3}(?:[., ]\d{3})+)(?:[.,](\d{1,2}))?", s)
    if m:  # a separator followed by exactly three digits is a thousands separator
        whole = re.sub(r"[., ]", "", m.group(1))
        return float(f"{whole}.{m.group(2) or 0}")
    return float(s.replace(",", "."))


def parse_annual_salary(text: str | None) -> float | None:
    """Gross EUR per year from free salary text; the upper value of a range. None = unknown."""
    if not text or _NON_EUR_RE.search(text):
        return None
    tokens = [(_to_float(m.group(1)), bool(m.group(2))) for m in _NUM_RE.finditer(text)]
    if not tokens:
        return None
    if any(k for _, k in tokens):  # "55-65k": a bare small number in a k-range is also thousands
        tokens = [(v * 1000 if (k or v < 1000) else v, True) for v, k in tokens]
    values = [v for v, _ in tokens]

    if _HOURLY_RE.search(text):
        factors = [HOURS_PER_YEAR] * len(values)
    elif _MONTHLY_RE.search(text):
        factors = [12] * len(values)
    elif _YEARLY_RE.search(text):
        factors = [1] * len(values)
    else:  # no unit given: infer from magnitude
        factors = [1 if v >= 15000 else 12 if v >= 1000 else HOURS_PER_YEAR if 8 <= v < 200 else 0
                   for v in values]
    annual = [v * f for v, f in zip(values, factors) if f and 5000 <= v * f <= 1_000_000]
    return round(max(annual), 2) if annual else None


def check_salary(salary_text: str | None, threshold: float) -> SalaryResult:
    annual = parse_annual_salary(salary_text)
    if annual is None:
        return SalaryResult(None, "salary_unknown")
    return SalaryResult(annual, "below_blue_card_threshold" if annual < threshold else "ok")


# --- Work authorization ----------------------------------------------------------------------

WORK_AUTH_PATTERNS = [
    r"unbefristete[nrs]?\s+arbeitserlaubnis",
    r"uneingeschränkte[nrs]?\s+arbeitserlaubnis",
    r"eu[\s-]?staatsbürgerschaft",
    r"eu[\s-]citizens?\s+only",
    r"no\s+visa\s+sponsorship",
    r"right\s+to\s+work\s+(?:in\s+[\w ]{2,25}?\s+)?without\s+(?:any\s+)?(?:visa\s+)?sponsorship",
    r"unrestricted\s+(?:work(?:ing)?\s+)?(?:authori[sz]ation|permit|right\s+to\s+work)",
]
_WORK_AUTH_RE = re.compile("|".join(f"(?:{p})" for p in WORK_AUTH_PATTERNS), re.IGNORECASE)


def check_work_authorization(*texts: str | None) -> str | None:
    """Return the matched phrase if the ad demands something the user must answer personally."""
    for text in texts:
        if text and (m := _WORK_AUTH_RE.search(text)):
            return m.group(0)
    return None
