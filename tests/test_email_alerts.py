"""Phase 9: email-alert source. Synthetic mails in the three LinkedIn formats seen in the user's
inbox (no real mail content is committed), and a fake IMAP server that records every command."""

import json
from datetime import date, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timezone

import pytest

from core import db
from core.dedup import canonical_url
from core.models import SearchFilter
from core.sources import SOURCES
from core.sources import email_alerts as ea

SEP = "---------------------------------------------------------"


def mail(sender, subject, plain, html="", mid="<m1@test>", days_ago=1):
    m = EmailMessage()
    m["From"] = f"LinkedIn <{sender}>"
    m["Subject"] = subject
    m["Message-ID"] = mid
    m["Date"] = format_datetime(datetime.now(timezone.utc) - timedelta(days=days_ago))
    m.set_content(plain)
    if html:
        m.add_alternative(html, subtype="html")
    return m


ALERT = mail("jobalerts-noreply@linkedin.com", "You may be a fit for ACME's Backend Developer role", f"""
Your job alert for Software Engineer in Germany
New jobs match your preferences.

Backend Developer (m/w/d)
ACME GmbH
Mannheim

2 school alumni
View job: https://www.linkedin.com/comm/jobs/view/4000000001/?trackingId=abc%3D&refId=x

{SEP}

Senior Principal Architect
Big Corp
Berlin

This company is actively hiring
View job: https://www.linkedin.com/comm/jobs/view/4000000002/?trackingId=def

{SEP}

See all jobs on LinkedIn: https://www.linkedin.com/comm/jobs/search/?keywords=x
""", html='<a href="https://www.linkedin.com/comm/jobs/view/4000000001/?t=1"></a>'
          '<a href="https://www.linkedin.com/comm/jobs/view/4000000001/?t=1">Backend Developer (m/w/d)</a>')

RECOMMENDATION = mail("jobs-noreply@linkedin.com", "TRUMPF hiring Embedded Software Engineer", f"""
Expand your search

Embedded jobs
https://www.linkedin.com/comm/jobs/search-results/?keywords=embedded

Embedded Software Engineer (w/m/d) C
TRUMPF
Freiburg
View job: https://www.linkedin.com/comm/jobs/view/4000000003/?trackingId=g

{SEP}
""", mid="<m2@test>")

HIRING = mail("messages-noreply@linkedin.com", "Developers: X is hiring", """
People with similar roles applied to these jobs
----------------------------------------
Python Developer
Example AG · Hamburg, Germany (Remote)
€60K-€70K / year
View
https://www.linkedin.com/comm/jobs/view/4000000004/?lipi=urn
""", mid="<m3@test>")


def test_parse_alert_format():
    jobs = ea.parse_linkedin(ALERT)
    assert [(j.title, j.company, j.location) for j in jobs] == [
        ("Backend Developer (m/w/d)", "ACME GmbH", "Mannheim"),
        ("Senior Principal Architect", "Big Corp", "Berlin")]
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/4000000001"   # tracking stripped, no request
    assert canonical_url(jobs[0].url) == "https://linkedin.com/jobs/view/4000000001"


def test_parse_recommendation_and_hiring_formats():
    [rec] = ea.parse_linkedin(RECOMMENDATION)
    assert (rec.title, rec.company, rec.location) == ("Embedded Software Engineer (w/m/d) C", "TRUMPF", "Freiburg")
    [hire] = ea.parse_linkedin(HIRING)
    assert (hire.title, hire.company, hire.location, hire.work_mode) == (
        "Python Developer", "Example AG", "Hamburg, Germany (Remote)", "remote")


class FakeIMAP:
    """Records commands; serves messages by UID. Any write command fails the test."""

    def __init__(self, messages):
        self.messages = {str(i + 1).encode(): m for i, m in enumerate(messages)}
        self.calls = []

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b"3"]

    def uid(self, cmd, *args):
        self.calls.append(("uid", cmd, *args))
        if cmd == "SEARCH":
            return "OK", [b" ".join(self.messages)]
        if cmd == "FETCH":
            uid, what = args
            assert "BODY.PEEK" in what, "must never fetch with BODY[] (would set \\Seen)"
            raw = self.messages[uid].as_bytes()
            return "OK", [(b"x", raw), b")"]
        raise AssertionError(f"unexpected IMAP command {cmd}")

    def logout(self):
        self.calls.append(("logout",))

    def __getattr__(self, name):  # store/copy/move/expunge/append/… → fail loudly
        raise AssertionError(f"read-only violated: IMAP {name}")


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBHUNTER_DB", str(tmp_path / "a.db"))
    c = db.connect()
    db.migrate(c)
    yield c
    c.close()


@pytest.fixture
def imap(monkeypatch):
    fake = FakeIMAP([ALERT, RECOMMENDATION, HIRING])
    monkeypatch.setattr(ea.mail_drafts, "connect", lambda cfg: fake)
    monkeypatch.setattr(ea.mail_config, "load_alerts_config", lambda: object())
    adapter = SOURCES["email_alerts"]
    adapter._cache = None
    return fake


def F(keywords, max_age=7):
    return SearchFilter(name="t", keywords=keywords, max_age_days=max_age, id=1)


def test_read_only_and_selection(conn, imap):
    jobs = SOURCES["email_alerts"].search(F(["Developer", "Engineer"]), 20)
    assert {j.title for j in jobs} == {"Backend Developer (m/w/d)", "Embedded Software Engineer (w/m/d) C", "Python Developer"}
    # EXAMINE (readonly), sender + SINCE search, PEEK fetches only
    assert ("select", '"INBOX"', True) in imap.calls
    search = next(c for c in imap.calls if c[:2] == ("uid", "SEARCH"))
    since = (date.today() - timedelta(days=ea.FIRST_RUN_DAYS)).strftime("%d-%b-%Y")
    assert search[2:5] == (None, "SINCE", since) and '"jobalerts-noreply@linkedin.com"' in search
    # processed Message-IDs recorded, last success advanced
    rows = {r["message_id"]: r["jobs_found"] for r in conn.execute("SELECT * FROM alert_messages")}
    assert rows == {"<m1@test>": 2, "<m2@test>": 1, "<m3@test>": 1}
    assert db.get_settings(conn)["email_alerts_last_success"] == date.today().isoformat()


def test_unmatched_jobs_are_not_returned(conn, imap):
    jobs = SOURCES["email_alerts"].search(F(["Embedded"]), 20)
    assert [j.title for j in jobs] == ["Embedded Software Engineer (w/m/d) C"]


def test_second_read_skips_processed_messages(conn, imap):
    SOURCES["email_alerts"].search(F(["Developer"]), 20)
    SOURCES["email_alerts"]._cache = None                 # next run = new process
    fetches_before = sum(1 for c in imap.calls if c[:2] == ("uid", "FETCH") and "BODY.PEEK[]" in c[3])
    SOURCES["email_alerts"].search(F(["Developer"]), 20)
    fetches_after = sum(1 for c in imap.calls if c[:2] == ("uid", "FETCH") and "BODY.PEEK[]" in c[3])
    assert fetches_after == fetches_before                # only headers were fetched again
    since = next(c for c in reversed(imap.calls) if c[:2] == ("uid", "SEARCH"))[4]
    assert since == date.today().strftime("%d-%b-%Y")      # SINCE last successful read


def test_old_mails_respect_max_age(conn, monkeypatch):
    old = mail("jobs-noreply@linkedin.com", "old", RECOMMENDATION.get_body(("plain",)).get_content(),
               mid="<old@test>", days_ago=10)
    fake = FakeIMAP([old])
    monkeypatch.setattr(ea.mail_drafts, "connect", lambda cfg: fake)
    monkeypatch.setattr(ea.mail_config, "load_alerts_config", lambda: object())
    SOURCES["email_alerts"]._cache = None
    assert SOURCES["email_alerts"].search(F(["Embedded"], max_age=7), 20) == []


def test_dry_run_records_nothing(conn, imap):
    adapter = SOURCES["email_alerts"]
    adapter.dry_run = True
    try:
        assert adapter.search(F(["Developer"]), 20)
    finally:
        adapter.dry_run = False
    assert conn.execute("SELECT COUNT(*) FROM alert_messages").fetchone()[0] == 0
    assert db.get_settings(conn)["email_alerts_last_success"] == ""


U1, U2 = "48b4a466-59e2-4eb4-a131-092fbfb0f59f", "0d08031a-0524-43c2-a8a2-2618760aca11"
INSTAFFO = mail("notifications@app.instaffo.com", "Android Developer oder lieber Senior Fullstack Developer?", f"""
[Logo](https://www.instaffo.com/?utm_term=logo)
Mehr Möglichkeiten für dich
[💡 Top Skill-Match](https://app.instaffo.com/candidate/job/{U1}?sso=deadbeef&utm_term=badge)
[Android Developer (m/f/d)](https://app.instaffo.com/candidate/job/{U1}?sso=deadbeef)
[[Logo]  Flexoptix GmbH](https://app.instaffo.com/candidate/job/{U1}?sso=deadbeef)      [Ort] Darmstadt
[Skills] Android Development, Kotlin
[[Gehalt] Entspricht deinem Wunschgehalt](https://app.instaffo.com/candidate/job/{U1}?sso=deadbeef)  [[Remote] Hybrid](https://app.instaffo.com/candidate/job/{U1}?sso=deadbeef)
[💰Top Gehalt](https://app.instaffo.com/candidate/job/{U2}?sso=deadbeef)
[Senior Fullstack Developer (m/w/d)](https://app.instaffo.com/candidate/job/{U2}?sso=deadbeef)
[[Logo]  Codefy GmbH](https://app.instaffo.com/candidate/job/{U2}?sso=deadbeef)      [Ort] Heidelberg
[Skills] Rust, React, JavaScript
[[Gehalt] 55.000 € – 80.000 €](https://app.instaffo.com/candidate/job/{U2}?sso=deadbeef)  [[Remote] Remote](https://app.instaffo.com/candidate/job/{U2}?sso=deadbeef)
[Alle Jobvorschläge auf Instaffo](https://app.instaffo.com/candidate/reonboarding?sso=deadbeef)
""", mid="<i1@test>")

INSTAFFO_OLD = mail("notifications@app.instaffo.com", "John, werde Senior Full Stack…", f"""
[Senior Full Stack Software Engineer (f/m/d)](https://app.instaffo.com/candidate/job/{U1}?sso=x)
[Company Logo](https://app.instaffo.com/candidate/job/{U1}?sso=x)	[[company-name] smartclip Europe GmbH](https://app.instaffo.com/candidate/job/{U1}?sso=x)
[[Location] Hamburg + 5 weitere](https://app.instaffo.com/candidate/job/{U1}?sso=x)
[[skills] Docker, Git, JavaScript](https://app.instaffo.com/candidate/job/{U1}?sso=x)
[[Salary] 65.000€ - 85.000€](https://app.instaffo.com/candidate/job/{U1}?sso=x)
""", mid="<i2@test>")

REMINDER = mail("notifications@app.instaffo.com", "57.000 € Wunschgehalt?",
                "Ist dein Wunschgehalt noch aktuell? [Jetzt anpassen](https://app.instaffo.com/candidate/settings?sso=x)",
                mid="<i3@test>")


def test_parse_instaffo_current_and_old_format_without_tokens():
    a, b = ea.parse_instaffo(INSTAFFO)
    assert (a.title, a.company, a.location, a.work_mode, a.salary_text) == (
        "Android Developer (m/f/d)", "Flexoptix GmbH", "Darmstadt", "hybrid", None)
    assert (b.title, b.company, b.location, b.work_mode, b.salary_text) == (
        "Senior Fullstack Developer (m/w/d)", "Codefy GmbH", "Heidelberg", "remote", "55.000 € – 80.000 €")
    assert "Skills: Rust, React, JavaScript" in b.description
    assert b.url == f"https://app.instaffo.com/candidate/job/{U2}" and "sso" not in a.url + b.url
    [old] = ea.parse_instaffo(INSTAFFO_OLD)
    assert (old.title, old.company, old.location, old.salary_text) == (
        "Senior Full Stack Software Engineer (f/m/d)", "smartclip Europe GmbH", "Hamburg + 5 weitere", "65.000€ - 85.000€")
    assert ea.parse_instaffo(REMINDER) == []          # not every Instaffo mail is a job alert


def test_instaffo_links_are_never_opened(conn, monkeypatch):
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("no HTTP request allowed"))
    fake = FakeIMAP([INSTAFFO, REMINDER])
    monkeypatch.setattr(ea.mail_drafts, "connect", lambda cfg: fake)
    monkeypatch.setattr(ea.mail_config, "load_alerts_config", lambda: object())
    conn.execute("UPDATE settings SET value = ? WHERE key = 'alert_senders'",
                 (json.dumps([{"board": "instaffo", "from": "notifications@app.instaffo.com"}]),))
    conn.commit()
    SOURCES["email_alerts"]._cache = None
    jobs = SOURCES["email_alerts"].search(F(["Developer"]), 20)
    assert len(jobs) == 2 and all("sso" not in j.url for j in jobs)
    assert jobs[1].salary_text == "55.000 € – 80.000 €"
    rows = {r["message_id"]: r["jobs_found"] for r in conn.execute("SELECT * FROM alert_messages")}
    assert rows == {"<i1@test>": 2, "<i3@test>": 0}   # the reminder is processed too, with 0 jobs


def test_sso_tokens_never_survive_canonicalisation():
    assert canonical_url(f"https://app.instaffo.com/candidate/job/{U1}?sso=abc&utm_term=x") == \
        f"https://app.instaffo.com/candidate/job/{U1}"
    assert "sso" not in canonical_url("https://example.com/job/1?sso=abc&id=7")


def test_imap_or_chain():
    assert ea._or_from(["a", "b", "c"]) == ["OR", "FROM", '"a"', "OR", "FROM", '"b"', "FROM", '"c"']


def test_stepstone_xing_canonical_ids():
    assert canonical_url("https://www.stepstone.de/stellenangebote--Backend-Entwickler-Mannheim-ACME--1234567-inline.html?rltr=x") \
        == "https://stepstone.de/stellenangebote--1234567"
    assert canonical_url("https://www.xing.com/jobs/mannheim-backend-developer-98765432?ijt=x") == "https://xing.com/jobs/98765432"


def test_filters_include_the_source(conn):
    from core.filters import seed_default_filters, load_filters
    seed_default_filters(conn)
    # migration 009 ran before seeding here, so seeding itself must include the source too
    assert all("email_alerts" in f.sources for f in load_filters(conn))
