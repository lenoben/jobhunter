"""Apply kit (§13): fields, files and prompt for a docs_ready job; work-authorization check."""

import pytest

from core import db
from mcp_server import server as s
from tests.test_mcp_tools import _examples, env, fake, shortlisted  # noqa: F401  (fixtures)


@pytest.fixture
def ready(shortlisted, env):
    cv, letter = _examples("de")
    s.render_documents(shortlisted, "de", cv, letter)
    s.save_application(shortlisted, "x", "- Q", "portal")
    assert s.get_job(shortlisted)["status"] == "docs_ready"
    return shortlisted


def test_kit_for_docs_ready_job(ready, env):
    kit = s.get_apply_kit(ready)
    fields = {f["label"]: f["value"] for f in kit["fields"]}
    # profile.example.yaml (set by the shortlisted fixture)
    assert fields["Name"] == "Max Mustermann"
    assert fields["First name / Vorname"] == "Max" and fields["Last name / Nachname"] == "Mustermann"
    assert fields["Email"].endswith("@myyahoo.com") and fields["Postcode / PLZ"] == "68159"
    assert fields["Earliest start / Eintrittstermin"] == "ab sofort" and fields["Hours per week / Wochenstunden"] == "40"
    assert fields["Salary expectation / Gehaltsvorstellung"].startswith("55.000")
    # motivation = the tailored opening of this job's letter
    assert fields["Motivation (short)"].startswith("Logistikprozesse zuverlässig")
    out = env / "output" / str(ready)
    B = "Max_Mustermann_Backend_Developer_"
    assert [d["path"] for d in kit["documents"]] == [str(out / f"{B}Lebenslauf.pdf"), str(out / f"{B}Anschreiben.pdf")]
    assert [d["label"] for d in kit["documents"]] == ["Lebenslauf", "Anschreiben"]
    assert kit["url"] == "https://jobs.example/1"
    p = kit["prompt"]
    assert "Do not click the final submit button" in p
    assert "Leave any work-authorization, visa or sponsorship questions empty and point them out to me." in p
    assert str(out / f"{B}Anschreiben.pdf") in p and "Max Mustermann" in p


@pytest.mark.parametrize("text,hit", [
    ("Voraussetzung: uneingeschränkte Arbeitserlaubnis für Deutschland", "uneingeschränkte Arbeitserlaubnis"),
    ("Applicants must have the right to work without sponsorship.", "right to work without sponsorship"),
    ("Do you need visa sponsorship? ( ) yes ( ) no", None),  # a question, not a demand
])
def test_check_work_authorization(text, hit):
    m = s.check_work_authorization(text)["match"]
    assert (m.lower() if m else None) == (hit.lower() if hit else None)


def test_flag_from_live_form(ready):
    s.flag_attention(ready, "work_authorization", 'Form demands: "uneingeschränkte Arbeitserlaubnis"')
    job = s.get_job(ready)
    assert job["status"] == "needs_attention" and job["attention_reason"] == "work_authorization"
