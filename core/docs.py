"""Render CV + cover letter (Typst → PDF) into output/<job_id>/ (CLAUDE.md §7).

Layout lives in templates/*.typ, content comes in as JSON (Claude only writes content). Checks
here are deterministic: schema, page limits (CV ≤ 2, letter = 1), no visa talk unless the posting
raises it, and every inferred fact (R5/R9) listed with its basis for the user to approve.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from core.applications import LETTER_FILES, classify_document, document_filename, output_dir, output_root
from core.db import ROOT

TEMPLATES = ROOT / "templates"
EXAMPLES = TEMPLATES / "examples"
MAX_PAGES = {"cv": 2, "letter": 1}
MIN_PAGES = {"cv": 1, "letter": 1}
_MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December")

# §7: never mention visa / residence / work authorization unless the posting asks for it.
VISA_RE = re.compile(
    r"\b(visa|visum|aufenthalts(?:titel|erlaubnis|genehmigung|recht)|blue\s*card|blauen?\s*karte|"
    r"arbeitserlaubnis|arbeitsgenehmigung|work\s*permit|residence\s*permit|"
    r"work\s*authori[sz]ation|sponsorship|right\s*to\s*work)\b", re.IGNORECASE)

CV_SCHEMA = {
    "name": str, "headline": str, "summary": str,
    "contact": dict, "personal": list, "experience": list, "education": list, "projects": list,
    "skills": list, "languages": list, "certificates": list, "inferred": list,
}
LETTER_SCHEMA = {
    "sender": dict, "recipient": dict, "place": str, "date": str, "subject": str, "reference": str,
    "salutation": str, "body": list, "closing": str, "attachments": list, "inferred": list,
}


class DocumentError(ValueError):
    pass


# ── validation ──────────────────────────────────────────────────────────────

def _check_types(kind: str, content: dict, schema: dict, required: tuple[str, ...]) -> None:
    if not isinstance(content, dict):
        raise DocumentError(f"{kind}_content must be a JSON object")
    unknown = sorted(set(content) - set(schema))
    if unknown:
        raise DocumentError(f"{kind}_content has unknown keys {unknown}; allowed: {sorted(schema)}")
    for key in required:
        if not content.get(key):
            raise DocumentError(f"{kind}_content.{key} is required")
    for key, typ in schema.items():
        if content.get(key) is not None and not isinstance(content[key], typ):
            raise DocumentError(f"{kind}_content.{key} must be a {typ.__name__}")


def validate_cv(c: dict) -> None:
    _check_types("cv", c, CV_SCHEMA, ("name", "experience", "education"))
    for i, e in enumerate(c.get("experience", [])):
        if not isinstance(e, dict) or not e.get("title"):
            raise DocumentError(f"cv_content.experience[{i}] needs a title")
    for key in ("skills",):
        for i, s in enumerate(c.get(key, [])):
            if not isinstance(s, dict) or not isinstance(s.get("items", []), list):
                raise DocumentError(f"cv_content.{key}[{i}] must be {{group, items: [..]}}")


def validate_letter(c: dict) -> None:
    _check_types("letter", c, LETTER_SCHEMA, ("sender", "recipient", "subject", "salutation", "body"))
    if not all(isinstance(p, str) and p.strip() for p in c["body"]):
        raise DocumentError("letter_content.body must be a list of non-empty paragraphs")
    if not isinstance(c["recipient"].get("lines"), list) or not c["recipient"]["lines"]:
        raise DocumentError("letter_content.recipient.lines must list the address lines")
    if re.match(r"\s*(betreff|subject)\s*:", c["subject"], re.IGNORECASE):
        raise DocumentError("subject must not start with 'Betreff:'/'Subject:' (DIN 5008)")


def inferred_facts(*contents: dict) -> list[dict]:
    """R5/R9: every statement not literally backed by profile.yaml, with where it is and why it is
    implied. These need the user's approval before the documents are used."""
    out = []
    for kind, c in zip(("cv", "letter"), contents):
        for i, f in enumerate(c.get("inferred") or []):
            if not isinstance(f, dict) or not (f.get("text") or "").strip() or not (f.get("basis") or "").strip():
                raise DocumentError(f"{kind}_content.inferred[{i}] needs 'text' and 'basis' (and ideally 'where')")
            out.append({"document": kind, "text": f["text"].strip(), "where": (f.get("where") or "").strip(),
                        "basis": f["basis"].strip()})
    return out


# R9 (a): an inferred fact is a capability/learning statement, never claimed experience, years,
# employers, grades or certificates.
R9_FORBIDDEN = re.compile(
    r"\b\d+\s*\+?\s*(?:jahre?n?|years?|yrs)\b|zertifi|certif|\bnote\b|\bgrade\b|\bgpa\b|"
    r"berufserfahrung\s+(?:bei|als)|work(?:ed)?\s+(?:at|for)\b", re.IGNORECASE)


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", s.casefold()).split())


def _strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return []


def check_inferred_rules(inferred: list[dict], contents: tuple[dict, ...], rejected: list[dict]) -> None:
    """R9: no forbidden kinds of inferred claims, and no reuse of statements the user rejected."""
    for f in inferred:
        if m := R9_FORBIDDEN.search(f["text"]):
            raise DocumentError(f"inferred fact {f['text']!r} claims {m.group(0)!r}; R9 allows only capability or "
                                "learning statements (no years, employers, grades or certificates)")
    if not rejected:
        return
    text = " | ".join(_norm(s) for c in contents
                      for s in _strings({k: v for k, v in c.items() if k != "inferred"}))
    for r in rejected:
        n = _norm(r["text"])
        if n and (n in text or any(_norm(f["text"]) == n for f in inferred)):
            raise DocumentError(f"the documents reuse {r['text']!r}, which the user rejected earlier (R9); leave it out")


def visa_mentions(content: dict) -> list[str]:
    text = json.dumps({k: v for k, v in content.items() if k != "inferred"}, ensure_ascii=False)
    return sorted({m.group(0) for m in VISA_RE.finditer(text)})


def _month_key(value) -> tuple[int, int]:
    """'MM/YYYY' → (YYYY, MM); 'present'/'heute' sorts first; unknown sorts last."""
    s = str(value or "").strip().lower()
    if s in ("present", "heute", "today", "now"):
        return (9999, 12)
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    return (int(m.group(2)), int(m.group(1))) if m else (0, 0)


def newest_first(entries: list) -> list:
    """Reverse-chronological order (§7), done in code so it doesn't depend on the model:
    by end date, then start date, newest first."""
    return sorted(entries, key=lambda e: (_month_key(e.get("to") or e.get("from")), _month_key(e.get("from"))),
                  reverse=True)


def format_date(d: date, lang: str) -> str:
    return f"{d:%d.%m.%Y}" if lang == "de" else f"{d.day} {_MONTHS_EN[d.month - 1]} {d.year}"


# ── rendering ───────────────────────────────────────────────────────────────

def compile_pdf(template: str, data: dict) -> tuple[bytes, int]:
    """Compile templates/<template>.typ with `data` as JSON input. Returns (pdf, page count)."""
    import typst

    path = TEMPLATES / f"{template}.typ"
    inputs = {"data": json.dumps(data, ensure_ascii=False)}
    try:
        pdf = typst.compile(str(path), root=str(ROOT), sys_inputs=inputs)
        pages = json.loads(typst.query(str(path), "<jh-pagecount>", field="value", one=True,
                                       root=str(ROOT), sys_inputs=inputs))
    except typst.TypstError as e:
        raise DocumentError(f"Typst failed for {template}: {e}") from None
    return pdf, int(pages)


def _photo_for_typst(photo: Path | None) -> str | None:
    if not photo:
        return None
    photo = (ROOT / photo).resolve() if not Path(photo).is_absolute() else Path(photo).resolve()
    if not photo.exists():
        raise DocumentError(f"profile photo {photo} does not exist")
    try:
        return "/" + photo.relative_to(ROOT).as_posix()  # Typst paths are relative to root
    except ValueError:
        raise DocumentError("the profile photo must be inside the project folder") from None


# ── cover-letter style rules (CLAUDE.md §7, rules 1, 7, 8, 9) ───────────────

CLICHE_RE = re.compile(
    r"mit\s+(?:gro(?:ß|ss)em|besonderem|regem)\s+interesse|hiermit\s+bewerbe\s+ich\s+mich|"
    r"bewerbe\s+ich\s+mich\s+hiermit|i\s+am\s+writing\s+to\s+(?:apply|express)|i\s+am\s+applying\s+for|"
    r"i\s+would\s+like\s+to\s+apply|please\s+accept\s+(?:this|my)\s+(?:letter|application)",
    re.IGNORECASE)
_MONTHS = ("januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember|"
           "january|february|march|may|june|july|october|december")
AVAILABILITY_RE = re.compile(
    rf"\b\d{{1,2}}\.\s?\d{{1,2}}\.\s?\d{{4}}\b|\b(?:{_MONTHS})\b[\s,]*\d{{4}}|\d{{1,2}}\.?\s+(?:{_MONTHS})|"
    r"ab\s+sofort|\bsofort\b|immediately|right\s+away|\bkurzfristig\b", re.IGNORECASE)
BODY_PARAGRAPHS = (4, 5)


def _url_key(url: str) -> str:
    return re.sub(r"^(?:https?://)?(?:www\.)?", "", url.strip().lower()).rstrip("/")


def _project_names(p: dict) -> list[str]:
    """Distinctive name variants of a profile project ('ChronosHub (kalender)' → 'chronoshub', 'kalender')."""
    names = set()
    for key in ("name", "name_en"):
        n = (p.get(key) or "").strip()
        if not n:
            continue
        names.add(n.casefold())
        names.add(re.sub(r"\s*\(.*?\)\s*", " ", n).strip().casefold())
        names.update(m.casefold() for m in re.findall(r"\(([^)]+)\)", n))
    return [n for n in names if len(n) >= 5]


def check_letter_style(letter: dict, projects: list[dict] | None = None) -> None:
    body = letter.get("body") or []
    lo, hi = BODY_PARAGRAPHS
    if not lo <= len(body) <= hi:
        raise DocumentError(f"the letter has {len(body)} body paragraphs; write {lo}–{hi} short ones (§7 rule 7)")
    opening = " ".join([letter.get("salutation") or "", body[0]])
    if m := CLICHE_RE.search(opening):
        raise DocumentError(f"the letter opens with the cliché {m.group(0)!r}; start with a motivation tied to "
                            "this role and company (§7 rule 1)")
    if not AVAILABILITY_RE.search(body[-1]):
        raise DocumentError("the last paragraph must state availability / the start date from the profile "
                            "(e.g. 'ab 01.02.2027' or 'ab sofort') (§7 rule 8)")
    text = " ".join(body).casefold()
    text_keys = _url_key(" ".join(body))
    for p in projects or []:
        url = p.get("url")
        if not url:
            continue
        if any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text) for n in _project_names(p)) \
                and _url_key(url) not in text_keys:
            raise DocumentError(f"the letter mentions the project {p.get('name')!r} without its link {url} "
                                "(§7 rule 9)")


def render_pair(out_dir: Path, doc_language: str, cv_content: dict | None, letter_content: dict | None,
                posting_text: str | None = None, photo: Path | None = None,
                rejected: list[dict] | None = None, projects: list[dict] | None = None,
                person: str | None = None, job_title: str | None = None) -> dict:
    """Render the CV and/or the letter (at least one; the user may ask for only one of them).
    The output folder then holds exactly the rendered documents."""
    if doc_language not in LETTER_FILES:
        raise DocumentError("doc_language must be 'de' or 'en'")
    if not cv_content and not letter_content:
        raise DocumentError("give cv_content and/or letter_content")
    contents = tuple(c for c in (cv_content, letter_content) if c)
    if cv_content:
        validate_cv(cv_content)
    if letter_content:
        validate_letter(letter_content)
        check_letter_style(letter_content, projects)
    inferred = inferred_facts(*(c or {} for c in (cv_content, letter_content)))
    check_inferred_rules(inferred, contents, rejected or [])

    if not (posting_text and VISA_RE.search(posting_text)):
        hits = [h for c in contents for h in visa_mentions(c)]
        if hits:
            raise DocumentError(f"documents mention {sorted(set(hits))}, but the posting doesn't ask "
                                "about visa/work authorization (§7: no visa talk in the first application)")

    data = {}
    if letter_content:
        data["letter"] = dict(letter_content)
        data["letter"].setdefault("date", format_date(date.today(), doc_language))
    if cv_content:
        cv = dict(cv_content)
        for key in ("experience", "education"):
            cv[key] = newest_first(cv.get(key) or [])
        # German CV: photo only if profile.yaml sets one. English CVs never carry a photo.
        cv["photo"] = _photo_for_typst(photo) if doc_language == "de" else None
        data["cv"] = cv

    rendered, problems = {}, []
    for kind in ("cv", "letter"):
        if kind not in data:
            continue
        pdf, pages = compile_pdf(f"{kind}_{doc_language}", data[kind])
        if not MIN_PAGES[kind] <= pages <= MAX_PAGES[kind]:
            problems.append(f"{kind} has {pages} pages (allowed: {MAX_PAGES[kind]}); shorten the content")
        rendered[kind] = (pdf, pages)
    if problems:
        raise DocumentError("; ".join(problems))

    out_dir.mkdir(parents=True, exist_ok=True)
    person = person or (cv_content or {}).get("name") or ((letter_content or {}).get("sender") or {}).get("name") or ""
    paths = {k: out_dir / document_filename(person, job_title or "", k, doc_language) for k in ("cv", "letter")}
    # The folder holds exactly this render: drop documents from an earlier render (other language,
    # other title, legacy names, or a document not requested this time).
    keep = {paths[k] for k in rendered}
    for old in out_dir.iterdir():
        if old.is_file() and classify_document(old.name) and old not in keep:
            old.unlink()
    for kind, (pdf, _pages) in rendered.items():
        paths[kind].write_bytes(pdf)
    (out_dir / "content.json").write_text(json.dumps(
        {"doc_language": doc_language, "cv": cv_content, "letter": data.get("letter"), "inferred": inferred},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return {"doc_language": doc_language, "inferred": inferred,
            "cv_path": str(paths["cv"]) if "cv" in rendered else None,
            "letter_path": str(paths["letter"]) if "letter" in rendered else None,
            "cv_pages": rendered["cv"][1] if "cv" in rendered else None,
            "letter_pages": rendered["letter"][1] if "letter" in rendered else None}


def render(job_id: int, doc_language: str, cv_content: dict | None, letter_content: dict | None,
           posting_text: str | None = None, photo: Path | None = None,
           rejected: list[dict] | None = None, projects: list[dict] | None = None,
           person: str | None = None, job_title: str | None = None) -> dict:
    return render_pair(output_dir(job_id), doc_language, cv_content, letter_content, posting_text, photo,
                       rejected, projects, person, job_title)


def render_test() -> list[dict]:
    """Render the committed example data (templates/examples/) in both languages."""
    results = []
    for lang in ("de", "en"):
        cv = json.loads((EXAMPLES / f"cv_{lang}.json").read_text(encoding="utf-8"))
        letter = json.loads((EXAMPLES / f"letter_{lang}.json").read_text(encoding="utf-8"))
        title = "Backend-Entwickler (m/w/d)" if lang == "de" else "Backend Engineer (Go)"
        results.append(render_pair(output_root() / "_render-test" / lang, lang, cv, letter, job_title=title))
    return results
