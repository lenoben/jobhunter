import json

import pytest

from core.applications import classify_document, document_filename
from core import docs
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


@pytest.mark.parametrize("lang,ats,expected", [("en", True, True), ("en", False, False), ("de", True, False)])
def test_ats_layout_is_for_english_cvs_only(tmp_path, monkeypatch, lang, ats, expected):
    """core §16e: the setting cv_ats_friendly reaches the template for English CVs; the Lebenslauf stays tabular."""
    seen = {}
    monkeypatch.setattr(docs, "compile_pdf", lambda template, data: seen.update(data) or (b"%PDF", 1))
    cv = json.loads((docs.EXAMPLES / f"cv_{lang}.json").read_text(encoding="utf-8"))
    docs.render_pair(tmp_path, lang, cv, None, ats=ats)
    assert seen["ats"] is expected


def test_ats_default_is_off_with_germany_as_a_target(tmp_path, monkeypatch):
    from core import db
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "a.db"))
    db.init_db()
    conn = db.connect()
    assert db.get_settings(conn)["cv_ats_friendly"] == "0"
    conn.close()
