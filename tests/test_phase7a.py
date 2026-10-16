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
