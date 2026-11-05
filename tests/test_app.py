from datetime import date, datetime, timedelta

import pytest

from casework import create_app
from casework.models import Case, Entry, db


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def make_case(app, days_old=0, **kw):
    with app.app_context():
        c = Case(case_number=kw.pop("case_number", f"CASE-{days_old}"), title="Broken thing",
                 product="Widget", version="1.0", operating_system="Windows 11",
                 opened_on=date.today() - timedelta(days=days_old), **kw)
        db.session.add(c)
        db.session.commit()
        return c.id


def test_create_case_and_view(client):
    r = client.post("/cases/new", data={
        "case_number": "12345", "title": "VPN drops", "product": "SecureVPN", "version": "3.1",
        "operating_system": "macOS 15", "status": "New", "opened_on": date.today().isoformat(),
    }, follow_redirects=True)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "12345" in body and "SecureVPN" in body and "macOS 15" in body
    for tab in ("Initial Response", "Scoping Q&amp;A", "Troubleshooting", "Meeting Summaries", "Other Notes"):
        assert tab in body


def test_case_validation(client, app):
    r = client.post("/cases/new", data={"case_number": "", "title": "", "product": "", "opened_on": ""},
                    follow_redirects=True)
    assert "Case number is required" in r.get_data(as_text=True)
    make_case(app, case_number="DUP")
    r = client.post("/cases/new", data={"case_number": "DUP", "title": "x", "product": "p",
                                        "opened_on": date.today().isoformat()}, follow_redirects=True)
    assert "already exists" in r.get_data(as_text=True)


def test_edit_case_with_error_does_not_persist(client, app):
    cid = make_case(app, case_number="EDIT")
    r = client.post(f"/cases/{cid}/edit", data={"case_number": "EDIT", "title": "", "product": "Widget",
                                                 "opened_on": date.today().isoformat()})
    assert "Title is required" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Case, cid).title == "Broken thing"


def test_add_edit_delete_entries(client, app):
    cid = make_case(app)
    when = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r = client.post(f"/cases/{cid}/entries/troubleshooting", data={
        "occurred_at": when, "title": "Remote session", "duration_minutes": "45",
        "body": "Collected logs", "findings": "Error 0x80070005", "next_steps": "Check perms",
    })
    assert r.status_code == 302 and r.location.endswith("#tab-troubleshooting")
    client.post(f"/cases/{cid}/entries/scoping", data={"occurred_at": when, "question": "When did it start?"})
    client.post(f"/cases/{cid}/entries/meeting", data={"occurred_at": when, "title": "Sync", "body": "Discussed"})
    client.post(f"/cases/{cid}/entries/initial_response", data={"occurred_at": when, "body": "Hello"})
    client.post(f"/cases/{cid}/entries/note", data={"occurred_at": when, "title": "FYI", "body": "VIP customer"})

    # missing required field is rejected
    client.post(f"/cases/{cid}/entries/troubleshooting", data={"occurred_at": when, "title": "No body"})

    with app.app_context():
        case = db.session.get(Case, cid)
        assert len(case.entries) == 5
        ts = case.entries_of("troubleshooting")[0]
        assert ts.duration_minutes == 45
        eid = ts.id

    client.post(f"/entries/{eid}/edit", data={"occurred_at": when, "title": "Remote session v2",
                                              "body": "Collected logs", "duration_minutes": "60"})
    with app.app_context():
        assert db.session.get(Entry, eid).title == "Remote session v2"
    client.post(f"/entries/{eid}/delete")
    with app.app_context():
        assert db.session.get(Entry, eid) is None

    assert client.post(f"/cases/{cid}/entries/bogus", data={}).status_code == 404


def test_standard_scoping_questions_idempotent(client, app):
    cid = make_case(app)
    client.post(f"/cases/{cid}/scoping/standard")
    client.post(f"/cases/{cid}/scoping/standard")
    with app.app_context():
        assert len(db.session.get(Case, cid).entries_of("scoping")) == 8


@pytest.mark.parametrize("days,stage", [(0, None), (4, None), (5, "swarm"), (14, "swarm"),
                                        (15, "structured_investigation"), (30, "structured_investigation")])
def test_escalation_thresholds(app, days, stage):
    cid = make_case(app, days_old=days)
    with app.app_context():
        assert db.session.get(Case, cid).escalation_stage == stage


def test_dashboard_flags(client, app):
    make_case(app, days_old=6, case_number="SWARM-ME")
    make_case(app, days_old=16, case_number="SI-ME")
    make_case(app, days_old=20, case_number="DONE", status="Closed", closed_on=date.today())
    body = client.get("/").get_data(as_text=True)
    assert "SWARM-ME" in body and "SI-ME" in body and "DONE" not in body
    assert "Swarm report" in body and "SI report" in body
    assert "DONE" in client.get("/?status=closed").get_data(as_text=True)


def test_swarm_report_contains_everything(client, app):
    cid = make_case(app, days_old=6, problem_description="App crashes", help_needed="Need SME")
    with app.app_context():
        c = db.session.get(Case, cid)
        base = datetime.combine(c.opened_on, datetime.min.time())
        db.session.add_all([
            Entry(case=c, entry_type="initial_response", occurred_at=base + timedelta(hours=9), body="Acked"),
            Entry(case=c, entry_type="scoping", occurred_at=base + timedelta(hours=10), question="Since when?",
                  response="Monday"),
            Entry(case=c, entry_type="troubleshooting", occurred_at=base + timedelta(days=2, hours=10),
                  title="Log review", body="Read logs", findings="Null ref in module X", duration_minutes=90),
            Entry(case=c, entry_type="meeting", occurred_at=base + timedelta(days=3), title="Call",
                  body="Agreed plan", action_items="Me: send build"),
            Entry(case=c, entry_type="note", occurred_at=base + timedelta(days=4), title="Note", body="Important"),
        ])
        db.session.commit()

    md = client.get(f"/cases/{cid}/report/swarm").get_data(as_text=True)
    for s in ["Swarm Request", "App crashes", "Need SME", "Acked", "Since when?", "Monday", "Log review",
              "Null ref in module X", "1h 30m", "Agreed plan", "Me: send build", "Important",
              "Day 1", "Day 3", "Day 4", "Day 5"]:
        assert s in md, s

    r = client.get(f"/cases/{cid}/report/swarm?download=1")
    assert r.mimetype == "text/markdown"
    assert "attachment" in r.headers["Content-Disposition"]
    assert r.get_data(as_text=True).startswith("# Swarm Request")


def test_structured_investigation_report(client, app):
    cid = make_case(app, days_old=16)
    with app.app_context():
        c = db.session.get(Case, cid)
        db.session.add(Entry(case=c, entry_type="troubleshooting", occurred_at=datetime.now() - timedelta(days=10),
                             title="Repro | lab", body="Tried", findings="Finding A\nFinding B"))
        db.session.add(Entry(case=c, entry_type="scoping", question="Unanswered?"))
        db.session.commit()
    r = client.get(f"/cases/{cid}/report/structured_investigation?download=1")
    md = r.get_data(as_text=True)
    for s in ["# Structured Investigation", "Executive Summary", "Escalation History", "Chronological Timeline",
              "Key Findings", "- Day 7 (Repro | lab): Finding A", "Finding B", "Gaps & Open Questions",
              "awaiting a response", "Repro \\| lab"]:
        assert s in md, s


def test_report_unknown_kind(client, app):
    cid = make_case(app)
    assert client.get(f"/cases/{cid}/report/nope").status_code == 404
    assert client.get("/cases/999").status_code == 404


def test_delete_case_cascades(client, app):
    cid = make_case(app)
    client.post(f"/cases/{cid}/entries/note", data={"title": "x", "body": "y"})
    client.post(f"/cases/{cid}/delete")
    with app.app_context():
        assert db.session.get(Case, cid) is None
        assert Entry.query.count() == 0


def test_basic_auth_when_configured():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                      "CASEWORK_USERNAME": "me", "CASEWORK_PASSWORD": "s3cret"})
    c = app.test_client()
    assert c.get("/").status_code == 401
    assert c.get("/", auth=("me", "wrong")).status_code == 401
    assert c.get("/", auth=("me", "s3cret")).status_code == 200


def test_no_auth_by_default(client):
    assert client.get("/").status_code == 200
