import pytest

from core.applications import classify_document, document_filename
from core.docs import newest_first


@pytest.mark.parametrize("title,kind,lang,expected", [
    ("Webentwickler React / Angular (m/w/d)", "cv", "de", "Max_Mustermann_Webentwickler_React_Angular_Lebenslauf.pdf"),
    ("Webentwickler React / Angular (all gender)", "letter", "de", "Max_Mustermann_Webentwickler_React_Angular_Anschreiben.pdf"),
    ("Frontend Engineer - Agentic AI", "cv", "en", "Max_Mustermann_Frontend_Engineer_Agentic_AI_CV.pdf"),
    ("Entwickler für Größenmessung (w/m/d)", "letter", "en", "Max_Mustermann_Entwickler_fuer_Groessenmessung_Cover_Letter.pdf"),
])
def test_document_filename(title, kind, lang, expected):
    name = document_filename("Max Mustermann", title, kind, lang)
    assert name == expected and classify_document(name) == (kind, lang)


def test_classify_rejects_other_files():
    assert classify_document("notes.md") is None and classify_document("../x_CV.pdf") is None
    assert classify_document("cv.pdf") == ("cv", None)  # legacy name still recognised


def test_newest_first_orders_like_a_lebenslauf():
    # Same shape as the order a model once produced: a lab job (to 06/2024) listed after 2023 internships.
    entries = [
        {"title": "Head of IT", "from": "04/2025", "to": "present"},
        {"title": "Frontend contract", "from": "01/2025", "to": "04/2025"},
        {"title": "Freelance", "from": "06/2024", "to": "03/2025"},
        {"title": "Internship A", "from": "07/2023", "to": "10/2023"},
        {"title": "Internship B", "from": "07/2023", "to": "09/2023"},
        {"title": "University lab", "from": "09/2023", "to": "06/2024"},
        {"title": "Part-time job", "from": "02/2026", "to": "present"},
    ]
    assert [e["title"] for e in newest_first(entries)] == [
        "Part-time job", "Head of IT", "Frontend contract", "Freelance", "University lab", "Internship A", "Internship B"]


def test_unknown_dates_go_last():
    assert [e["t"] for e in newest_first([{"t": "x", "from": "?"}, {"t": "y", "from": "01/2020", "to": "02/2020"}])] == ["y", "x"]
