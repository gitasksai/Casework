"""Load a few sample cases so you can see the app in action: python seed.py"""
from datetime import date, datetime, timedelta

from casework import create_app
from casework.models import Case, Entry, db

app = create_app()


def at(days_ago, hour=10):
    d = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    return d - timedelta(days=days_ago)


with app.app_context():
    if Case.query.filter_by(case_number="SAMPLE-1001").first():
        print("Sample data already loaded.")
        raise SystemExit

    fresh = Case(case_number="SAMPLE-1001", title="Login page slow after upgrade", customer="Contoso",
                 product="WebPortal", version="4.2.1", operating_system="Ubuntu 22.04",
                 severity="3 - Medium", status="In Progress", opened_on=date.today() - timedelta(days=2),
                 problem_description="Login takes 20-30s since upgrade to 4.2.1.")
    swarm = Case(case_number="SAMPLE-1002", title="Service crashes nightly during backup", customer="Fabrikam",
                 product="DataSync Server", version="7.0.3", operating_system="Windows Server 2022",
                 severity="2 - High", status="In Progress", opened_on=date.today() - timedelta(days=6),
                 problem_description="DataSync service terminates around 02:00 every night with exception 0xc0000005.",
                 business_impact="Nightly replication fails; 3 branch offices work on stale data each morning.",
                 current_status="Crash dump collected; faulting module looks like a third-party backup filter driver.",
                 next_steps="Get dump analysed; test with backup agent filter disabled.",
                 help_needed="Need a debugging SME to confirm the faulting stack and whether it is a known issue.")
    si = Case(case_number="SAMPLE-1003", title="Intermittent data corruption in exports", customer="Northwind",
              product="ReportHub", version="12.1", operating_system="RHEL 9.4",
              severity="1 - Critical", status="Swarm", opened_on=date.today() - timedelta(days=17),
              problem_description="About 1 in 200 CSV exports contain truncated rows.",
              business_impact="Regulatory reports to finance are wrong; customer is manually verifying every export.")
    db.session.add_all([fresh, swarm, si])

    db.session.add_all([
        Entry(case=swarm, entry_type="initial_response", occurred_at=at(6, 9), title="Acknowledged",
              body="Acknowledged the issue, requested Application/System event logs and service logs."),
        Entry(case=swarm, entry_type="scoping", occurred_at=at(6, 10), question="When did the crashes start?",
              response="After installing backup agent update 5.4 two weeks ago."),
        Entry(case=swarm, entry_type="scoping", occurred_at=at(6, 10), question="Is it every night?",
              response="Yes, every night between 01:55 and 02:10."),
        Entry(case=swarm, entry_type="scoping", occurred_at=at(6, 10), question="Can we disable the backup temporarily?"),
        Entry(case=swarm, entry_type="troubleshooting", occurred_at=at(5, 14), title="Log review", duration_minutes=60,
              body="Reviewed event logs and DataSync logs.\nCorrelated crash time with backup job start.",
              findings="Event 1000: faulting module bkfilter.sys offset 0x1a2b.\nCrash 2 minutes after backup starts.",
              next_steps="Configure ProcDump to capture crash dump."),
        Entry(case=swarm, entry_type="troubleshooting", occurred_at=at(3, 15), title="Dump collection", duration_minutes=45,
              body="Configured ProcDump -e -ma on the service.", findings="Full dump captured overnight.",
              next_steps="Analyse dump."),
        Entry(case=swarm, entry_type="meeting", occurred_at=at(2, 16), title="Status call", attendees="Customer IT lead, me",
              body="Reviewed findings; customer agrees to test with filter driver disabled.",
              action_items="Customer: disable bkfilter on test server\nMe: engage swarm for dump analysis"),
        Entry(case=swarm, entry_type="note", occurred_at=at(1), title="Similar case",
              body="Possibly related to an older case with the same backup vendor."),
        Entry(case=si, entry_type="initial_response", occurred_at=at(17), body="Acknowledged and requested sample bad exports."),
        Entry(case=si, entry_type="troubleshooting", occurred_at=at(12), title="Reproduce in lab", duration_minutes=180,
              body="Ran 1000 exports against a copy of the DB.", findings="Reproduced 4 truncations, all with rows > 64KB."),
        Entry(case=si, entry_type="meeting", occurred_at=at(11), title="Swarm session", attendees="Swarm team",
              body="Swarm reviewed; suspect buffer limit in export writer.", action_items="Dev: review export buffer code"),
    ])
    db.session.commit()
    print("Loaded 3 sample cases (2, 6 and 17 days old).")
