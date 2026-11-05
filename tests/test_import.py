import json
from datetime import datetime
from pathlib import Path

import pytest

from casework import create_app
from casework.importer import build_plan, clean_body, parse_datetime
from casework.models import Case, Entry, ImportBatch, db

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "salesforce_capture.json").read_text())


@pytest.fixture
def app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


@pytest.fixture
def client(app):
    return app.test_client()


def _by_text(plan, needle):
    return next(i for i in plan["items"] if needle in (i["clean"] or ""))


def test_plan_maps_case_fields(app):
    with app.app_context():
        case = build_plan(FIXTURE)["case"]
    assert case["case_number"] == "480570091"
    assert case["title"].startswith("Unable to sign in")
    assert case["customer"] == "Acme Corp"
    assert case["product"] == "Tableau Desktop & Prep Builder-Connecting to Data / Desktop Authentication-Single Sign-On"
    assert case["version"] == "2024.2.3"
    assert case["operating_system"] == "Windows 11"
    assert case["severity"] == "2 - High"
    assert case["status"] == "In Progress"
    assert case["opened_on"].isoformat() == "2026-11-02"


def test_plan_classifies_feed(app):
    with app.app_context():
        plan = build_plan(FIXTURE)
    assert plan["engineer"] == "Sathishkumar Ashok"  # from Case Owner
    first = _by_text(plan, "Thank you for contacting Tableau Support")
    assert first["category"] == "initial_response" and first["include"]
    assert "Which version of Tableau Desktop" in first["question"]
    assert "Tableau Desktop 2024.2.3" in first["response"]
    assert "Best regards" not in first["clean"]
    reply = _by_text(plan, "Please find the details")
    assert not reply["include"] and reply["consumed_by"] == first["key"]
    assert "earlier message" not in reply["clean"] and "Thanks" not in reply["clean"]
    assert _by_text(plan, "Summary of today's call")["category"] == "meeting"
    assert _by_text(plan, "AudienceRestriction")["category"] == "troubleshooting"
    assert _by_text(plan, "any update on this case")["reason"] == "Follow-up / reminder"
    assert _by_text(plan, "Thank you for sharing the requested details")["reason"].startswith("Acknowledgement")
    assert _by_text(plan, "System Generated Feed")["reason"].startswith("Automated")
    assert _by_text(plan, "changed Status from New")["reason"] == "Status or field change"
    times = [i["when"] for i in plan["items"]]
    assert times == sorted(times)


@pytest.mark.parametrize("text,expected", [
    ("20h ago", datetime(2026, 11, 4, 16, 0)),
    ("3d ago", datetime(2026, 11, 2, 12, 0)),
    ("Yesterday at 9:15 AM", datetime(2026, 11, 4, 9, 15)),
    ("November 3, 2026 at 4:30 PM", datetime(2026, 11, 3, 16, 30)),
    ("11/3/2026, 4:30 PM", datetime(2026, 11, 3, 16, 30)),
    ("2/11/2026, 9:30 AM", datetime(2026, 2, 11, 9, 30)),  # month/day unless told otherwise
    ("25/10/2026 09:30", datetime(2026, 10, 25, 9, 30)),  # only valid as day/month
    ("2026-11-03T10:00", datetime(2026, 11, 3, 10, 0)),
    ("not a date", None),
])
def test_parse_datetime(text, expected):
    assert parse_datetime(text, datetime(2026, 11, 5, 12, 0)) == expected


def test_day_first_detection():
    now = datetime(2026, 11, 5, 12, 0)
    from casework.importer import detect_day_first
    assert detect_day_first({"fields": [{"label": "Opened", "value": "25/10/2026 09:30"}]}, now) is True
    assert detect_day_first({"fields": [{"label": "Opened", "value": "10/25/2026 9:30 AM"}]}, now) is False
    # ambiguous dates, settled by comparing with the "3d ago" labels
    feed = [{"timeText": "3d ago", "timeTitle": "2/11/2026 12:00"}, {"timeText": "1d ago", "timeTitle": "4/11/2026 12:00"}]
    assert detect_day_first({"feed": feed}, now) is True
    plan_day_first = {"fields": [{"label": "Date/Time Opened", "value": "2/11/2026 09:30"}], "feed": feed,
                      "capturedAt": "2026-11-05T12:00:00"}
    assert build_plan(plan_day_first)["case"]["opened_on"].isoformat() == "2026-11-02"


def test_clean_body_strips_greeting_signature_and_quotes():
    body = "Hi Alex,\n\nThe fix is to update the audience URI.\n\nRegards,\nSathish\n\nOn Mon wrote:\n> old"
    assert clean_body(body) == "The fix is to update the audience URI."


def test_api_import_review_and_apply(client, app):
    r = client.post("/api/import", json=FIXTURE)
    assert r.status_code == 200 and r.json["ok"]
    assert r.json["counts"]["included"] == 4
    review = r.json["reviewUrl"].replace("http://localhost", "")
    page = client.get(review).get_data(as_text=True)
    assert "Review import" in page and "Follow-up / reminder" in page

    with app.app_context():
        from casework.importer import build_plan as bp
        plan = bp(FIXTURE)
    form = {f"include_{i['key']}": "1" for i in plan["items"] if i["include"]}
    form.update({f"cat_{i['key']}": i["category"] for i in plan["items"]})
    for name, value in [("case_number", "480570091"), ("title", plan["case"]["title"]), ("product", plan["case"]["product"]),
                        ("version", "2024.2.3"), ("operating_system", "Windows 11"), ("status", "In Progress"),
                        ("severity", "2 - High"), ("opened_on", "2026-11-02"), ("customer", "Acme Corp")]:
        form[f"apply_{name}"] = "1"
        form[f"value_{name}"] = value
    r = client.post(review, data=form)
    assert r.status_code == 302

    with app.app_context():
        case = Case.query.filter_by(case_number="480570091").one()
        assert case.opened_on.isoformat() == "2026-11-02" and case.version == "2024.2.3"
        types = sorted(e.entry_type for e in case.entries)
        assert types == ["initial_response", "meeting", "note", "scoping", "troubleshooting"]
        scoping = case.entries_of("scoping")[0]
        assert "Which version" in scoping.question and "2024.2.3" in scoping.response
        assert db.session.query(ImportBatch).one().applied_at is not None
        imported_keys = {i.key for i in case.imported_items}
        assert len(imported_keys) == 5  # 4 items + the reply used as the scoping answer

    # Capturing the same case again: everything already imported is skipped.
    r = client.post("/api/import", json=FIXTURE)
    assert r.json["counts"]["included"] == 4  # counts are computed before the case lookup
    page = client.get(r.json["reviewUrl"].replace("http://localhost", "")).get_data(as_text=True)
    assert "Already imported earlier" in page and "Updating existing case" in page
    r = client.post(r.json["reviewUrl"].replace("http://localhost", ""), data={})
    with app.app_context():
        assert Entry.query.count() == 5


def test_api_rejects_empty(client):
    assert client.post("/api/import", json={}).status_code == 400


def test_api_token_required_when_login_enabled():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                      "CASEWORK_USERNAME": "me", "CASEWORK_PASSWORD": "pw"})
    c = app.test_client()
    assert c.get("/api/ping").status_code == 401  # login on, no token configured
    app.config["CASEWORK_API_TOKEN"] = "t0ken"
    assert c.get("/api/ping").status_code == 401
    assert c.get("/api/ping", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/ping", headers={"Authorization": "Bearer t0ken"}).json["ok"]
    # the review page still requires the normal login
    assert c.get("/import/abc").status_code == 401
