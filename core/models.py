"""Plain dataclasses shared by core, the MCP server and the CLI."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Literal

WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
EmploymentType = Literal["full_time", "part_time", "minijob", "working_student", "internship"]
ApplyMethod = Literal["portal", "email", "external_ats", "unknown"]

JOB_STATUSES = (
    "new", "skipped", "shortlisted", "docs_ready", "needs_attention",
    "applied", "feedback", "interview", "offer", "rejected", "withdrawn",
)
# feedback: the employer replied after the application, but not (yet) with an interview (2026-10-21)
USER_ONLY_STATUSES = ("applied", "feedback", "interview", "offer", "rejected", "withdrawn")
ATTENTION_REASONS = (
    "needs_login", "captcha", "form_unclear", "missing_profile_info",
    "german_only_form", "source_error", "work_authorization", "below_blue_card_threshold",
    "inferred_facts", "alert_review",
)
SALARY_FLAGS = ("ok", "below_blue_card_threshold", "salary_unknown")


@dataclass
class SearchFilter:
    name: str
    keywords: list[str]
    exclude_keywords: list[str] = field(default_factory=list)
    location: str | None = None              # None = Germany-wide
    radius_km: int = 50
    work_modes: list[str] = field(default_factory=lambda: ["remote", "hybrid", "onsite"])
    employment_types: list[str] = field(default_factory=lambda: ["full_time"])
    exclude_freelance: bool = True
    languages: list[str] = field(default_factory=lambda: ["de", "en"])
    sources: list[str] = field(default_factory=lambda: ["ba_jobsuche", "arbeitnow", "jobspy", "email_alerts"])
    max_age_days: int = 7
    min_fit_score: int = 60
    active: bool = True
    id: int | None = None

    _JSON_FIELDS = ("keywords", "exclude_keywords", "work_modes", "employment_types", "languages", "sources")

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> SearchFilter:
        d = dict(row)
        for k in cls._JSON_FIELDS:
            d[k] = json.loads(d[k])
        d["active"] = bool(d["active"])
        d["exclude_freelance"] = bool(d["exclude_freelance"])
        d.pop("created_at", None)
        d.pop("updated_at", None)
        return cls(**d)

    def to_db(self) -> dict:
        """Column values for INSERT/UPDATE (without id/timestamps)."""
        return {
            "name": self.name,
            "active": int(self.active),
            "keywords": json.dumps(self.keywords, ensure_ascii=False),
            "exclude_keywords": json.dumps(self.exclude_keywords, ensure_ascii=False),
            "location": self.location,
            "radius_km": self.radius_km,
            "work_modes": json.dumps(self.work_modes),
            "employment_types": json.dumps(self.employment_types),
            "exclude_freelance": int(self.exclude_freelance),
            "languages": json.dumps(self.languages),
            "sources": json.dumps(self.sources),
            "max_age_days": self.max_age_days,
            "min_fit_score": self.min_fit_score,
        }


@dataclass
class JobPosting:
    """A normalised posting as returned by a source adapter (before/after DB insert)."""
    source: str
    url: str
    title: str
    company: str | None = None
    location: str | None = None
    source_job_id: str | None = None
    description: str | None = None
    salary_text: str | None = None
    salary_annual_eur: float | None = None   # §5a: normalised gross EUR/year (upper value of a range)
    salary_flag: str | None = None           # ok | below_blue_card_threshold | salary_unknown
    posted_at: str | None = None             # ISO date/datetime
    work_mode: str | None = None
    employment_type: str | None = None
    language: str | None = None
    apply_method: str | None = None
    apply_email: str | None = None
    # Set once stored / evaluated
    id: int | None = None
    canonical_url: str | None = None
    fingerprint: str | None = None
    fit_score: int | None = None
    fit_notes: str | None = None
    status: str = "new"
    attention_reason: str | None = None
    filter_id: int | None = None
    first_seen_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> JobPosting:
        return cls(**dict(row))


@dataclass
class Application:
    job_id: int
    cv_path: str | None = None
    letter_path: str | None = None
    doc_language: str | None = None
    summary: str | None = None
    interview_prep: str | None = None
    method: str | None = None
    email_draft_saved: bool = False
    applied_at: str | None = None
    inferred_facts: list[dict] = field(default_factory=list)   # R5/R9, need the user's approval
    inferred_approved_at: str | None = None
    id: int | None = None
    created_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Application:
        d = dict(row)
        d["email_draft_saved"] = bool(d["email_draft_saved"])
        d["inferred_facts"] = json.loads(d.get("inferred_facts") or "[]")
        return cls(**d)


@dataclass
class Run:
    trigger: str                             # scheduled | manual
    found: int = 0
    new_jobs: int = 0
    tailored: int = 0
    needs_you: int = 0
    errors: list[dict] = field(default_factory=list)   # [{source, message}]
    status: str = "running"                  # running | ok | partial | failed
    id: int | None = None
    started_at: str | None = None
    finished_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Run:
        d = dict(row)
        d["errors"] = json.loads(d["errors"] or "[]")
        return cls(**d)
