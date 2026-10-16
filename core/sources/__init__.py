"""Importing this package registers every adapter in SOURCES. Adding a board = one new file + one line here."""

from core.sources.base import SOURCES, Source, SourceError  # noqa: F401
from core.sources import ba_jobsuche  # noqa: F401
from core.sources import arbeitnow  # noqa: F401
from core.sources import jobspy_source  # noqa: F401
from core.sources import email_alerts  # noqa: F401
