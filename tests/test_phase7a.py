"""Phase 7a: letter style rules, single-document renders, document requests, project suggestions."""

import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from core import db, jobs
from core.docs import DocumentError, check_letter_style
from mcp_server import server as s
from tests.test_mcp_tools import _examples, env, fake, shortlisted  # noqa: F401  (fixtures)

PROJECTS = [{"name": "Buchungskalender (kalender)", "url": "https://github.com/example/kalender"},
            {"name": "Reise-Marktplatz", "url": "https://reise-marktplatz.example"}]


def _letter(body):
    return {"salutation": "Sehr geehrte Damen und Herren,", "body": body}


GOOD = ["Ihre Plattform für X reizt mich, weil …", "Bei Reise-Marktplatz (reise-marktplatz.example) habe ich …",
        "Für Buchungskalender (github.com/example/kalender) habe ich …", "Ich kann ab 01.02.2027 in Vollzeit beginnen."]


def test_good_letter_passes():
    check_letter_style(_letter(GOOD), PROJECTS)


@pytest.mark.parametrize("opener", ["mit großem Interesse habe ich Ihre Anzeige gelesen.",
                                    "hiermit bewerbe ich mich als Entwickler.",
                                    "I am writing to apply for the role.", "I am applying for the position."])
def test_cliche_openers_refused(opener):
    with pytest.raises(DocumentError, match="cliché"):
        check_letter_style(_letter([opener] + GOOD[1:]), PROJECTS)


@pytest.mark.parametrize("n", [3, 6])
def test_paragraph_count(n):
    body = (GOOD[:-1] * 3)[: n - 1] + [GOOD[-1]]
    with pytest.raises(DocumentError, match="body paragraphs"):
        check_letter_style(_letter(body), PROJECTS)


def test_closing_needs_availability():
    with pytest.raises(DocumentError, match="start date"):
        check_letter_style(_letter(GOOD[:-1] + ["Ich freue mich auf ein Gespräch."]), PROJECTS)
    for ok in ("Ich kann ab sofort beginnen.", "I can start immediately.", "Ab Februar 2027 verfügbar.",
               "Available from 1 February 2027."):
        check_letter_style(_letter(GOOD[:-1] + [ok]), PROJECTS)


def test_mentioned_project_needs_link():
    body = list(GOOD)
    body[2] = "Für Buchungskalender habe ich eine REST-API gebaut."
    with pytest.raises(DocumentError, match="without its link https://github.com/example/kalender"):
        check_letter_style(_letter(body), PROJECTS)
    body[2] = "Mein Kalender-Projekt kalender (https://github.com/example/kalender/) zeigt …"
    check_letter_style(_letter(body), PROJECTS)


def test_request_documents_and_writer_list(shortlisted):
    c = db.connect()
    try:
        c.execute("UPDATE jobs SET fit_score = 55 WHERE id = ?", (shortlisted,))
        c.commit()
        assert jobs.list_jobs(c, "shortlisted", for_documents=True) == []  # 55 < 60 (default min_fit_for_documents)
        assert [j["id"] for j in jobs.list_jobs(c, "shortlisted")] == [shortlisted]

        skipped = s.is_seen("https://jobs.example/3")["job_id"]   # the freelance job, skipped by prefilter
        jobs.request_documents(c, skipped, "cv")
        jobs.request_documents(c, shortlisted, "both")
        rows = jobs.list_jobs(c, "shortlisted", for_documents=True)
        assert {r["id"]: r["docs_requested"] for r in rows} == {skipped: "cv", shortlisted: "both"}
        assert jobs.get_job(c, skipped)["status"] == "shortlisted"
        with pytest.raises(ValueError, match="which must be one of"):
            jobs.request_documents(c, skipped, "photo")
    finally:
        c.close()


def test_cv_only_request_renders_only_the_cv(shortlisted, env):
    c = db.connect()
    jobs.request_documents(c, shortlisted, "cv")
    c.close()
    cv, letter = _examples("de")
    with pytest.raises(ToolError, match="CV only"):
        s.render_documents(shortlisted, "de", cv, letter)
    r = s.render_documents(shortlisted, "de", cv_content=cv)
    out = env / "output" / str(shortlisted)
    assert r["letter_path"] is None
    assert [p.name for p in out.glob("*.pdf")] == ["Max_Mustermann_Backend_Developer_Lebenslauf.pdf"]
    app = s.save_application(shortlisted, "CV only, as requested.", "- Q", "portal")
    assert app["letter_path"] is None and s.get_job(shortlisted)["docs_requested"] is None


def test_default_is_cv_only_unless_the_user_picks(shortlisted, env):
    """2026-10-22: runs write only the CV unless the setting default_documents is 'both' or the user
    picked documents for the job."""
    c = db.connect()
    c.execute("UPDATE settings SET value = 'cv' WHERE key = 'default_documents'")
    c.commit()
    assert [(r["id"], r["documents"]) for r in jobs.list_jobs(c, "shortlisted", for_documents=True)] == [(shortlisted, "cv")]
    assert s.get_job(shortlisted)["documents"] == "cv"
    cv, letter = _examples("de")
    with pytest.raises(ToolError, match="CV only"):
        s.render_documents(shortlisted, "de", cv, letter)
    jobs.request_documents(c, shortlisted, "both")          # the user's per-job choice wins
    assert s.get_job(shortlisted)["documents"] == "both"
    assert s.render_documents(shortlisted, "de", cv, letter)["letter_path"]
    c.execute("UPDATE settings SET value = 'nonsense' WHERE key = 'default_documents'")
    assert jobs.documents_to_write(c, None) == "cv"
    c.close()


def test_project_suggestions_stored_and_validated(fake):
    s.search_jobs(1, sources=["fake"])
    job_id = s.is_seen("https://jobs.example/1")["job_id"]
    ideas = [{"title": "K8s demo", "scope": "Deploy Buchungskalender on k3s", "days": 3, "covers": "Kubernetes"}]
    with pytest.raises(ToolError, match="needs title, scope, days and covers"):
        s.evaluate_job(job_id, 75, "ok", "remote", "full_time", "de", "portal", "shortlist",
                       project_suggestions=[{"title": "x"}])
    s.evaluate_job(job_id, 75, "ok", "remote", "full_time", "de", "portal", "shortlist", project_suggestions=ideas)
    assert s.get_job(job_id)["project_suggestions"] == ideas


def test_current_run_tool():
    assert s.current_run() == {"run_id": None}
    run_id = s.start_run("manual")["run_id"]
    assert s.current_run() == {"run_id": run_id}


def test_file_names_use_first_and_last_name_only():
    """2026-10-22: only the first word of the name and the last name."""
    from core.applications import classify_document, document_filename
    name = document_filename("Max Peter Mustermann", "Backend Developer (m/w/d)", "cv", "de")
    assert name == "Max_Mustermann_Backend_Developer_Lebenslauf.pdf"
    assert document_filename("Cher", "Dev", "letter", "en") == "Cher_Dev_Cover_Letter.pdf"
    motivation = document_filename("Max Peter Mustermann", "Dev", "motivation", "de")
    assert motivation == "Max_Mustermann_Dev_Motivationsschreiben.pdf"
    assert classify_document(motivation) == ("motivation", "de")
    assert classify_document("Max_Mustermann_Dev_Motivation_Letter.pdf") == ("motivation", "en")


def test_motivation_only_on_request_and_keeps_cv_and_letter(shortlisted, env):
    """2026-10-22: a Motivationsschreiben is written only when the user asks; it leaves the CV and
    letter in place, and later CV/letter renders keep it."""
    cv, letter = _examples("de")
    motivation = json.loads((db.ROOT / "templates/examples/motivation_de.json").read_text(encoding="utf-8"))
    with pytest.raises(ToolError, match="only when the user asks"):
        s.render_documents(shortlisted, "de", cv, letter, motivation_content=motivation)
    s.render_documents(shortlisted, "de", cv, letter)
    s.save_application(shortlisted, "CV + letter.", "- Q", "portal")

    c = db.connect()
    jobs.request_documents(c, shortlisted, "motivation")
    c.close()
    assert s.get_job(shortlisted)["documents"] == "motivation"
    with pytest.raises(ToolError, match="Motivationsschreiben only"):
        s.render_documents(shortlisted, "de", cv_content=cv, motivation_content=motivation)
    with pytest.raises(ToolError, match="body paragraphs"):
        s.render_documents(shortlisted, "de", motivation_content=motivation | {"body": motivation["body"][:2]})
    r = s.render_documents(shortlisted, "de", motivation_content=motivation)
    assert r["motivation_pages"] in (1, 2)
    out = env / "output" / str(shortlisted)
    B = "Max_Mustermann_Backend_Developer_"
    assert sorted(p.name for p in out.glob("*.pdf")) == [B + "Anschreiben.pdf", B + "Lebenslauf.pdf", B + "Motivationsschreiben.pdf"]
    app = s.save_application(shortlisted, "CV + letter. Motivationsschreiben added.", "- Q", "portal")
    assert app["motivation_path"].endswith("Motivationsschreiben.pdf") and app["letter_path"]

    s.render_documents(shortlisted, "de", cv, letter)     # a new CV/letter render keeps it
    assert (out / (B + "Motivationsschreiben.pdf")).exists()
    content = json.loads((out / "content.json").read_text(encoding="utf-8"))
    assert content["motivation"]["subtitle"] == motivation["subtitle"]


def test_single_document_render_keeps_the_other(shortlisted, env):
    """2026-10-22: "cover letter only" after a CV adds the letter; it no longer deletes the CV.
    A render in the other language still replaces the old documents."""
    cv, letter = _examples("de")
    c = db.connect()
    jobs.request_documents(c, shortlisted, "cv")
    c.close()
    s.render_documents(shortlisted, "de", cv_content=cv)
    out = env / "output" / str(shortlisted)
    B = "Max_Mustermann_Backend_Developer_"
    cv_file = out / (B + "Lebenslauf.pdf")
    before = cv_file.read_bytes()

    c = db.connect()
    jobs.request_documents(c, shortlisted, "letter")
    c.close()
    s.render_documents(shortlisted, "de", letter_content=letter)
    assert sorted(p.name for p in out.glob("*.pdf")) == [B + "Anschreiben.pdf", B + "Lebenslauf.pdf"]
    assert cv_file.read_bytes() == before                      # the CV is untouched
    content = json.loads((out / "content.json").read_text(encoding="utf-8"))
    assert content["cv"] and content["letter"]
    app = s.save_application(shortlisted, "Letter added.", "- Q", "portal")
    assert app["cv_path"].endswith("Lebenslauf.pdf") and app["letter_path"].endswith("Anschreiben.pdf")

    c = db.connect()
    jobs.request_documents(c, shortlisted, "cv")
    c.close()
    cv_en, _ = _examples("en")
    s.render_documents(shortlisted, "en", cv_content=cv_en)     # other language: the German letter goes
    assert sorted(p.name for p in out.glob("*.pdf")) == [B + "CV.pdf"]
