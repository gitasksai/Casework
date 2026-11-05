from datetime import date, datetime

from flask import current_app
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

STATUSES = [
    "New",
    "In Progress",
    "Waiting on Customer",
    "Swarm",
    "Structured Investigation",
    "Resolved",
    "Closed",
]
CLOSED_STATUSES = {"Resolved", "Closed"}
SEVERITIES = ["1 - Critical", "2 - High", "3 - Medium", "4 - Low"]


class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    customer = db.Column(db.String(255))
    product = db.Column(db.String(255), nullable=False)
    version = db.Column(db.String(100))
    operating_system = db.Column(db.String(255))
    severity = db.Column(db.String(32))
    status = db.Column(db.String(64), nullable=False, default="New")
    opened_on = db.Column(db.Date, nullable=False, default=date.today)
    closed_on = db.Column(db.Date)

    # Narrative fields used heavily by the swarm / structured investigation reports
    problem_description = db.Column(db.Text)
    business_impact = db.Column(db.Text)
    current_status = db.Column(db.Text)
    next_steps = db.Column(db.Text)
    help_needed = db.Column(db.Text)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    entries = db.relationship(
        "Entry",
        backref="case",
        cascade="all, delete-orphan",
        order_by="Entry.occurred_at",
        lazy="select",
    )

    @property
    def is_closed(self):
        return self.status in CLOSED_STATUSES

    @property
    def age_days(self):
        end = self.closed_on or date.today()
        return max((end - self.opened_on).days, 0)

    def entries_of(self, entry_type):
        return [e for e in self.entries if e.entry_type == entry_type]

    @property
    def swarm_due(self):
        return self.age_days >= current_app.config["SWARM_AGE_DAYS"]

    @property
    def investigation_due(self):
        return self.age_days >= current_app.config["STRUCTURED_INVESTIGATION_AGE_DAYS"]

    @property
    def escalation_stage(self):
        """Highest escalation stage the case has reached based on age."""
        if self.investigation_due:
            return "structured_investigation"
        if self.swarm_due:
            return "swarm"
        return None

    def day_number(self, when):
        """1-based day of the case on which `when` happened (Day 1 = opened date)."""
        d = when.date() if isinstance(when, datetime) else when
        return (d - self.opened_on).days + 1


class Entry(db.Model):
    """A piece of work logged against a case.

    entry_type is one of the keys in casework.entry_types.ENTRY_TYPES. Not every
    column is used by every type (e.g. `question`/`response` are only for scoping).
    """

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("case.id"), nullable=False, index=True)
    entry_type = db.Column(db.String(32), nullable=False, index=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    title = db.Column(db.String(255))
    body = db.Column(db.Text)
    question = db.Column(db.Text)
    response = db.Column(db.Text)
    attendees = db.Column(db.String(500))
    action_items = db.Column(db.Text)
    findings = db.Column(db.Text)
    next_steps = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    @property
    def summary(self):
        text = self.title or self.question or self.body or ""
        first = text.strip().splitlines()[0] if text.strip() else ""
        return first if len(first) <= 120 else first[:117] + "..."
