import pytest

from core.checks import check_salary, check_work_authorization, parse_annual_salary

THRESHOLD = 45934.20


@pytest.mark.parametrize("text, expected", [
    ("50.000 € - 60.000 € brutto/Jahr", 60000),          # range → upper value
    ("50.000–60.000 EUR", 60000),
    ("55k-65k EUR", 65000),
    ("55-65k €", 65000),
    ("45.934,20 €", 45934.20),                            # German format
    ("€45,934.20 per year", 45934.20),                    # English format
    ("€ 3.500 monatlich", 42000),                         # monthly × 12
    ("3.500 - 4.200 € / Monat", 50400),
    ("4200 EUR per month", 50400),
    ("20 €/Std.", 41600),                                 # hourly × 40 × 52
    ("25 EUR per hour", 52000),
    ("3800 € brutto", 45600),                             # no unit → monthly by magnitude
    ("ab 60.000 EUR p.a.", 60000),
    ("60 Tsd. €", 60000),
])
def test_parse_annual_salary(text, expected):
    assert parse_annual_salary(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", [None, "", "attraktiv", "nach Vereinbarung", "$120,000", "£50,000", "CHF 100'000"])
def test_unknown_salary(text):
    assert parse_annual_salary(text) is None
    r = check_salary(text, THRESHOLD)
    assert r.flag == "salary_unknown" and r.annual_eur is None


def test_below_threshold():
    r = check_salary("40.000 - 45.000 €", THRESHOLD)
    assert r.flag == "below_blue_card_threshold" and r.annual_eur == 45000


def test_range_straddling_threshold_uses_upper_value():
    assert check_salary("40.000 - 55.000 €", THRESHOLD).flag == "ok"


def test_exact_threshold_is_ok():
    assert check_salary("45.934,20 € p.a.", THRESHOLD).flag == "ok"
    assert check_salary("45.934 € p.a.", THRESHOLD).flag == "below_blue_card_threshold"


def test_threshold_comes_from_caller():
    assert check_salary("48.000 €", 50700).flag == "below_blue_card_threshold"
    assert check_salary("48.000 €", THRESHOLD).flag == "ok"


@pytest.mark.parametrize("text", [
    "Voraussetzung: unbefristete Arbeitserlaubnis für Deutschland",
    "Sie besitzen eine uneingeschränkte Arbeitserlaubnis.",
    "EU-Staatsbürgerschaft erforderlich",
    "EU Staatsbürgerschaft",
    "EU citizen only",
    "EU citizens only, please.",
    "Unfortunately there is no visa sponsorship for this role.",
    "You have the right to work without sponsorship.",
    "You have the right to work in Germany without visa sponsorship.",
    "Candidates need unrestricted work authorization.",
])
def test_work_authorization_flags(text):
    assert check_work_authorization(text)


@pytest.mark.parametrize("text", [
    "We offer visa sponsorship and relocation support.",
    "Sehr gute Deutschkenntnisse (C1) erforderlich.",
    "Wir unterstützen dich bei Visum und Arbeitserlaubnis.",
    "Gültige Arbeitserlaubnis für Deutschland",
    None,
])
def test_work_authorization_no_flag(text):
    assert check_work_authorization(text) is None


def test_work_authorization_checks_all_texts():
    assert check_work_authorization("Backend Developer", "… no visa sponsorship …") == "no visa sponsorship"
