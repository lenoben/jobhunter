"""Load and validate profile/profile.yaml — the only source for generated documents (R5)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from core.db import ROOT

REQUIRED_SECTIONS = ("personal", "summary_de", "summary_en", "experience", "education", "skills",
                     "languages", "availability")
OPTIONAL_SECTIONS = ("projects", "certificates", "work_authorization", "preferences")
_DATE = re.compile(r"^(0[1-9]|1[0-2])/\d{4}$|^present$", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"<YOUR_|TODO|Max Mustermann|example\.com", re.IGNORECASE)


class ProfileError(Exception):
    pass


def profile_path() -> Path:
    override = os.environ.get("JOBHUNTER_PROFILE")
    return Path(override) if override else ROOT / "profile" / "profile.yaml"


def load_profile(path: Path | None = None) -> tuple[dict, list[str]]:
    """Return (profile, warnings). Raises ProfileError if the file is missing or unusable."""
    path = path or profile_path()
    if not path.exists():
        raise ProfileError(f"{path} not found; copy profile.example.yaml there and fill it in")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ProfileError(f"{path.name} is not valid YAML: {e}") from None
    if not isinstance(data, dict):
        raise ProfileError(f"{path.name} must be a mapping of sections")
    return data, validate(data)


def validate(p: dict) -> list[str]:
    missing = [s for s in REQUIRED_SECTIONS if not p.get(s)]
    if missing:
        raise ProfileError(f"profile is missing required section(s): {', '.join(missing)}")
    personal = p["personal"]
    if not isinstance(personal, dict) or not personal.get("name") or not personal.get("email"):
        raise ProfileError("personal.name and personal.email are required")

    warnings: list[str] = []
    for i, e in enumerate(p.get("experience") or []):
        for key in ("company", "role", "from"):
            if not e.get(key):
                warnings.append(f"experience[{i}] has no {key}")
        warnings += _dates(f"experience[{i}] ({e.get('company', '?')})", e)
    for i, e in enumerate(p.get("education") or []):
        warnings += _dates(f"education[{i}] ({e.get('institution', '?')})", e)
    for lang in p.get("languages") or []:
        if not lang.get("level"):
            warnings.append(f"language {lang.get('language', '?')} has no CEFR level")
    for path, value in _walk(p):
        if isinstance(value, str) and _PLACEHOLDER.search(value):
            warnings.append(f"{path} looks like a placeholder: {value[:60]!r}")
    return warnings


def _dates(label: str, entry: dict) -> list[str]:
    return [f"{label}.{k} is {entry[k]!r}, expected MM/YYYY or 'present'"
            for k in ("from", "to") if entry.get(k) and not _DATE.match(str(entry[k]))]


def _walk(node, path: str = ""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, node
