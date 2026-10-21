"""MCP tools called directly (the decorator returns the plain function), against a temp DB."""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from core import db
from core.filters import seed_default_filters
from core.models import JobPosting
from core.sources import SOURCES
from mcp_server import server as s
from tests.test_search import FakeSource, P


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    from core import notify
    monkeypatch.setattr(notify, "_config", lambda: ("", ""))  # never message the real Telegram chat
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("JOBHUNTER_OUTPUT", str(tmp_path / "output"))
    c = db.connect()
    db.migrate(c)
    seed_default_filters(c)
    c.close()
    yield tmp_path


@pytest.fixture
def fake():
    SOURCES["fake"] = FakeSource([
        P("https://jobs.example/1", "Backend Developer (m/w/d)", salary_text="60.000 €", description="Python."),
        P("https://jobs.example/2", "Python Developer", description="No visa sponsorship."),
        P("https://jobs.example/3", "Freelance Python Developer"),
    ])
    yield SOURCES["fake"]
    del SOURCES["fake"]


def _sql(query, *args):
    c = db.connect()
    try:
        return c.execute(query, args).fetchall()
    finally:
        c.close()


def test_run_time_guard():
    first = s.start_run("scheduled")
    assert first["started"] is True
    refused = s.start_run("scheduled")
    assert refused == {"started": False, "reason": refused["reason"]} and "still running" in refused["reason"]
    s.finish_run(first["run_id"])
    refused = s.start_run("manual")
    assert refused["started"] is False and "min_hours_between_runs" in refused["reason"]


def test_stale_running_run_is_closed():
    c = db.connect()
    c.execute("INSERT INTO runs (trigger, started_at) VALUES ('scheduled', datetime('now', '-5 hours'))")
    c.commit()
    c.close()
    assert s.start_run("scheduled")["started"] is True
    assert _sql("SELECT status FROM runs ORDER BY id")[0]["status"] == "failed"


def test_search_records_on_run_and_is_seen(fake):
    run_id = s.start_run("manual")["run_id"]
    r = s.search_jobs(1, sources=["fake"])
    assert r["run_id"] == run_id and r["skipped_by_prefilter"] == 1
    statuses = {j["title"]: j["status"] for j in r["new_jobs"]}
    assert statuses == {"Backend Developer (m/w/d)": "new", "Python Developer": "needs_attention"}

    assert s.search_jobs(1, sources=["fake"])["new_jobs"] == []  # R8: nothing twice
    seen = s.is_seen("https://jobs.example/1?utm_source=newsletter")
    assert seen["seen"] and seen["status"] == "new"
    assert s.is_seen("https://jobs.example/404") == {"seen": False}

    done = s.finish_run(run_id)
    assert done["status"] == "ok" and "6 found · 2 new" in done["summary"]  # two searches, 3 each
    assert "1 need you" in done["summary"] and done["telegram"] == "not configured"


def test_search_validates_input():
    with pytest.raises(ToolError, match="no search filter"):
        s.search_jobs(999)
    with pytest.raises(ToolError, match="unknown source"):
        s.search_jobs(1, sources=["monster"])


def test_evaluate_and_flag(fake):
    s.search_jobs(1, sources=["fake"])
    job_id = s.is_seen("https://jobs.example/1")["job_id"]
    kwargs = dict(fit_notes="Strong Python match.", work_mode="hybrid", employment_type="full_time",
                  language="de", apply_method="portal")
    with pytest.raises(ToolError, match="below the filter's min_fit_score"):
        s.evaluate_job(job_id, 40, decision="shortlist", **kwargs)
    with pytest.raises(ToolError, match="work_mode must be one of"):
        s.evaluate_job(job_id, 80, decision="shortlist", **(kwargs | {"work_mode": "office"}))
    assert s.evaluate_job(job_id, 80, decision="shortlist", **kwargs)["status"] == "shortlisted"
    with pytest.raises(ToolError, match="already scored"):
        s.evaluate_job(job_id, 80, decision="shortlist", **kwargs)

    s.flag_attention(job_id, "needs_login", "Portal requires an account.")
    job = s.get_job(job_id)
    assert job["status"] == "needs_attention" and job["attention_reason"] == "needs_login"
    assert [h["to_status"] for h in job["history"]] == ["new", "shortlisted", "needs_attention"]
    with pytest.raises(ToolError, match="reason must be one of"):
        s.flag_attention(job_id, "bored", "x")


def test_save_application_needs_documents_then_writes_notes(fake, env):
    s.search_jobs(1, sources=["fake"])
    job_id = s.is_seen("https://jobs.example/1")["job_id"]
    s.evaluate_job(job_id, 85, "Good fit.", "remote", "full_time", "de", "email", "shortlist",
                   apply_email="jobs@acme.example")
    with pytest.raises(ToolError, match="call render_documents first"):
        s.save_application(job_id, "Python emphasised.", "- Q1", "email")

    out = env / "output" / str(job_id)
    out.mkdir(parents=True)
    (out / "cv.pdf").write_bytes(b"%PDF-1.7")
    (out / "anschreiben.pdf").write_bytes(b"%PDF-1.7")
    app = s.save_application(job_id, "Python emphasised.", "- Q1", "email")
    assert app["doc_language"] == "de" and app["letter_path"].endswith("anschreiben.pdf")
    notes = (out / "notes.md").read_text(encoding="utf-8")
    assert "Good fit." in notes and "Python emphasised." in notes and "€60,000" in notes
    assert s.get_job(job_id)["status"] == "docs_ready"


def _examples(lang):
    import json
    ex = db.ROOT / "templates" / "examples"
    return (json.loads((ex / f"cv_{lang}.json").read_text(encoding="utf-8")),
            json.loads((ex / f"letter_{lang}.json").read_text(encoding="utf-8")))


@pytest.fixture
def shortlisted(fake, monkeypatch):
    monkeypatch.setenv("JOBHUNTER_PROFILE", str(db.ROOT / "profile.example.yaml"))  # photo: null
    s.search_jobs(1, sources=["fake"])
    job_id = s.is_seen("https://jobs.example/1")["job_id"]
    s.evaluate_job(job_id, 85, "Good fit.", "hybrid", "full_time", "de", "email", "shortlist",
                   apply_email="jobs@acme.example")
    c = db.connect()   # these tests write CV + letter; the default since 2026-10-22 is the CV only
    c.execute("UPDATE settings SET value = 'both' WHERE key = 'default_documents'")
    c.commit()
    c.close()
    return job_id


def test_render_then_save_gives_docs_ready(shortlisted, env):
    cv, letter = _examples("de")
    r = s.render_documents(shortlisted, "de", cv, letter)
    assert r["cv_pages"] <= 2 and r["letter_pages"] == 1 and r["inferred"] == []
    out = env / "output" / str(shortlisted)
    B = "Max_Mustermann_Backend_Developer_"  # <Name>_<Job title>_<Document>.pdf
    assert (out / f"{B}Lebenslauf.pdf").read_bytes().startswith(b"%PDF") and (out / f"{B}Anschreiben.pdf").exists()

    s.render_documents(shortlisted, "en", *_examples("en"))  # language switch replaces the letter
    assert sorted(p.name for p in out.glob("*.pdf")) == [f"{B}CV.pdf", f"{B}Cover_Letter.pdf"]

    app = s.save_application(shortlisted, "Go emphasised.", "- Q", "email")
    assert app["doc_language"] == "en" and app["inferred_facts"] == []
    assert s.get_job(shortlisted)["status"] == "docs_ready"


def test_inferred_facts_need_approval(shortlisted, env, monkeypatch):
    cv, letter = _examples("de")
    cv["skills"].append({"group": "Cloud", "items": ["Kubernetes (Grundlagen)"]})
    cv["inferred"] = [{"text": "Kubernetes (Grundlagen)", "where": "skills/Cloud",
                       "basis": "Docker Compose in production; container orchestration is the next step"}]
    r = s.render_documents(shortlisted, "de", cv, letter)
    assert r["inferred"][0]["text"] == "Kubernetes (Grundlagen)"

    s.save_application(shortlisted, "Go emphasised.", "- Q", "email")
    job = s.get_job(shortlisted)
    assert job["status"] == "needs_attention" and job["attention_reason"] == "inferred_facts"
    notes = (env / "output" / str(shortlisted) / "notes.md").read_text(encoding="utf-8")
    assert "need your approval" in notes and "Kubernetes (Grundlagen)" in notes

    with pytest.raises(ToolError, match="hasn't approved"):
        s.save_email_draft(shortlisted, "Bewerbung", "Text")

    from core import applications
    c = db.connect()
    applications.approve_inferred(c, shortlisted)
    c.close()
    assert s.get_job(shortlisted)["status"] == "docs_ready"


def test_save_email_draft_attaches_pdfs_and_never_sends(shortlisted, monkeypatch):
    from core import mail_drafts
    calls = []
    monkeypatch.setattr(mail_drafts, "create_draft", lambda **kw: calls.append(kw) or
                        {"folder": "Draft", "found_by": "\\Drafts flag", "message_id": "<x@y>", "confirmed": True})
    s.render_documents(shortlisted, "de", *_examples("de"))
    s.save_application(shortlisted, "Go emphasised.", "- Q", "email")
    r = s.save_email_draft(shortlisted, "Bewerbung als Backend Developer", "Sehr geehrte Damen und Herren, …")
    assert r["sent"] is False and r["saved_to"] == "Draft" and r["to"] == "jobs@acme.example"
    assert [p.name for p in calls[0]["attachments"]] == ["Max_Mustermann_Backend_Developer_Lebenslauf.pdf",
                                                         "Max_Mustermann_Backend_Developer_Anschreiben.pdf"]
    assert s.get_job(shortlisted)["application"]["email_draft_saved"] == 1


def test_save_email_draft_needs_application(shortlisted):
    with pytest.raises(ToolError, match="call save_application first"):
        s.save_email_draft(shortlisted, "Bewerbung", "Text")


def test_r9_only_capability_statements(shortlisted):
    cv, letter = _examples("de")
    letter["body"].insert(-1, "Ich habe 3 Jahre Erfahrung mit Kubernetes.")
    letter["inferred"] = [{"text": "3 Jahre Erfahrung mit Kubernetes", "where": "letter", "basis": "Docker"}]
    with pytest.raises(ToolError, match="R9 allows only capability"):
        s.render_documents(shortlisted, "de", cv, letter)


def test_rejected_inference_is_never_reused(shortlisted, env):
    from core import applications
    cv, letter = _examples("de")
    cv["skills"].append({"group": "Cloud", "items": ["Kubernetes (Grundlagen)"]})
    cv["inferred"] = [{"text": "Kubernetes (Grundlagen)", "where": "skills/Cloud", "basis": "Docker Compose"}]
    s.render_documents(shortlisted, "de", cv, letter)
    s.save_application(shortlisted, "x", "- Q", "email")
    c = db.connect()
    applications.reject_inferred(c, shortlisted, "not true")
    c.close()
    assert s.get_job(shortlisted)["status"] == "shortlisted"
    assert s.get_profile()["rejected_inferences"][0]["text"] == "Kubernetes (Grundlagen)"

    # same statement again — listed as inferred or silently put into the CV — is refused
    with pytest.raises(ToolError, match="rejected earlier"):
        s.render_documents(shortlisted, "de", cv, letter)
    cv["inferred"] = []
    with pytest.raises(ToolError, match="rejected earlier"):
        s.render_documents(shortlisted, "de", cv, letter)
    cv["skills"].pop()
    assert s.render_documents(shortlisted, "de", cv, letter)["inferred"] == []


def test_inferred_entry_needs_basis(shortlisted):
    cv, letter = _examples("de")
    cv["inferred"] = [{"text": "Kubernetes"}]
    with pytest.raises(ToolError, match="needs 'text' and 'basis'"):
        s.render_documents(shortlisted, "de", cv, letter)


def test_no_visa_talk_unless_posting_asks(shortlisted, fake):
    cv, letter = _examples("de")
    letter["body"].insert(-1, "Eine Arbeitserlaubnis liegt vor.")
    with pytest.raises(ToolError, match="no visa talk"):
        s.render_documents(shortlisted, "de", cv, letter)
    # job 2's posting says "No visa sponsorship" → mentioning it is allowed there
    other = s.is_seen("https://jobs.example/2")["job_id"]
    assert s.render_documents(other, "de", cv, letter)["letter_pages"] == 1


def test_page_limits_enforced(shortlisted, env):
    cv, letter = _examples("de")
    letter["body"] = [p * 6 for p in letter["body"]]  # same 4 paragraphs, far too long
    with pytest.raises(ToolError, match="letter has 2 pages"):
        s.render_documents(shortlisted, "de", cv, letter)
    assert not list((env / "output" / str(shortlisted)).glob("*.pdf")) if (env / "output" / str(shortlisted)).exists() else True


def test_render_rejects_bad_input(shortlisted):
    cv, letter = _examples("de")
    with pytest.raises(ToolError, match="doc_language"):
        s.render_documents(shortlisted, "fr", cv, letter)
    with pytest.raises(ToolError, match="unknown keys"):
        s.render_documents(shortlisted, "de", cv | {"photo": "C:/x.jpg"}, letter)
    with pytest.raises(ToolError, match="Betreff"):
        s.render_documents(shortlisted, "de", cv, letter | {"subject": "Betreff: Bewerbung"})


def test_get_profile_errors_cleanly(monkeypatch, env):
    monkeypatch.setenv("JOBHUNTER_PROFILE", str(env / "nope.yaml"))
    with pytest.raises(ToolError, match="not found"):
        s.get_profile()


def test_get_profile_example_validates(monkeypatch):
    monkeypatch.setenv("JOBHUNTER_PROFILE", str(db.ROOT / "profile.example.yaml"))
    p = s.get_profile()
    assert p["profile"]["personal"]["name"] and any("placeholder" in w for w in p["warnings"])


def test_get_active_filters():
    filters = s.get_active_filters()
    assert len(filters) == 6 and filters[0]["keywords"]
    assert "blue_card_salary_min" in s.get_settings()
