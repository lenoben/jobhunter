"""Apply kit (CLAUDE.md §13): everything the user (or the browser extension) needs to fill in an
application form — never to submit it (R1, R2). Mirrored for the UI in ui/src/lib/server/kit.ts.
"""

from __future__ import annotations

import json
import sqlite3

from core import applications, jobs

DOC_LABELS = {("cv", "de"): "Lebenslauf", ("cv", "en"): "CV", ("cv", None): "CV / Lebenslauf",
              ("letter", "de"): "Anschreiben", ("letter", "en"): "Cover letter"}

PROMPT_INTRO = (
    "Fill in this application form using the data below. Upload the CV and cover letter if the "
    "form allows it. Do not click the final submit button — stop and tell me when it is ready.\n"
    "Leave any work-authorization, visa or sponsorship questions empty and point them out to me.\n"
    "Do not log in, create an account or solve a CAPTCHA — stop and tell me instead.\n"
    "If the page demands unrestricted work authorization, EU citizenship, or says no visa "
    "sponsorship, stop and tell me the exact wording."
)


def build_kit(conn: sqlite3.Connection, job_id: int, profile: dict) -> dict:
    job = jobs.get_job(conn, job_id)
    row = conn.execute("SELECT name FROM search_filters WHERE id = ?", (job.get("filter_id"),)).fetchone()
    job["filter_name"] = row["name"] if row else None
    p = profile.get("personal") or {}
    addr = p.get("address") or {}
    av = profile.get("availability") or {}
    lang = job.get("language") or "de"
    name = (p.get("name") or "").strip()
    first, _, last = name.rpartition(" ")

    documents = [{"name": p.name, "label": DOC_LABELS[applications.classify_document(p.name)], "path": str(p)}
                 for p in applications.list_documents(job_id)]

    fields = [
        ("Name", name),
        ("First name / Vorname", first or name),
        ("Last name / Nachname", last if first else ""),
        ("Email", p.get("email")),
        ("Phone / Telefon", p.get("phone")),
        ("Street / Straße", addr.get("street")),
        ("Postcode / PLZ", addr.get("postal_code")),
        ("City / Ort", addr.get("city")),
        ("Country / Land", addr.get("country")),
        ("Address (one line)", ", ".join(x for x in (addr.get("street"),
                                                     f"{addr.get('postal_code', '')} {addr.get('city', '')}".strip(),
                                                     addr.get("country")) if x)),
        ("Earliest start / Eintrittstermin", av.get("start_date")),
        ("Hours per week / Wochenstunden", av.get("hours_per_week")),
        ("Salary expectation / Gehaltsvorstellung", (profile.get("preferences") or {}).get("salary_text")),
        ("LinkedIn", p.get("linkedin")),
        ("GitHub", p.get("github")),
        ("Website", p.get("website")),
        ("Motivation (short)", _motivation(job_id, job, profile, lang)),
    ]
    kit_fields = [{"label": k, "value": str(v).strip()} for k, v in fields if v not in (None, "")]

    data_block = "\n".join(f"- {f['label']}: {f['value']}" for f in kit_fields)
    docs_block = "\n".join(f"- {d['label']}: {d['path']}" for d in documents) or "- (no documents yet)"
    apply_url = job.get("apply_url") or job["url"]  # where to apply, if the user set one (migration 011)
    prompt = (f"{PROMPT_INTRO}\n\nJob: {job['title']} — {job.get('company') or ''}\nApplication page: {apply_url}\n\n"
              f"Data:\n{data_block}\n\nFiles to upload:\n{docs_block}")
    return {
        "job_id": job_id, "title": job["title"], "company": job.get("company"), "url": apply_url,
        "posting_url": job["url"],
        "apply_method": job.get("apply_method"), "apply_email": job.get("apply_email"),
        "language": lang, "documents": documents, "fields": kit_fields, "prompt": prompt,
    }


def _motivation(job_id: int, job: dict, profile: dict, lang: str) -> str | None:
    """Short motivation paragraph: the tailored opening of this job's letter if there is one,
    else the user's motivation for the job's filter category, else the profile summary."""
    content = applications.output_dir(job_id) / "content.json"
    if content.exists():
        letter = json.loads(content.read_text(encoding="utf-8")).get("letter") or {}
        if letter.get("body"):
            return letter["body"][0]
    own = (profile.get("motivation") or {}).get(job.get("filter_name") or "")
    if own and str(own).strip():
        return " ".join(str(own).split())
    summary = profile.get(f"summary_{lang}") or profile.get("summary_en")
    return " ".join(str(summary).split()) if summary else None
