# Build Casework from scratch in Visual Studio Code

This guide walks you through building the Casework app yourself, one file at a time, in
VS Code on Windows. At the end you'll have the same app that's in this repository: case
tracking with tabs for initial response, scoping, troubleshooting, meetings and notes, plus
swarm (5 days) and structured investigation (15 days) reports, tests, and an HTTPS server.

Every code block below is the **complete** file. Create the file at the path shown and paste
the whole block in.

**Time:** about 1-2 hours. **You need:** a Windows PC with internet access.

## Contents

1. [Install the tools](#1-install-the-tools)
2. [Create the project in VS Code](#2-create-the-project-in-vs-code)
3. [Create a virtual environment](#3-create-a-virtual-environment)
4. [Install the dependencies](#4-install-the-dependencies)
5. [Create the folder structure](#5-create-the-folder-structure)
6. [Write the data layer](#6-write-the-data-layer)
7. [Write the report generator](#7-write-the-report-generator)
8. [Write the web pages (routes)](#8-write-the-web-pages-routes)
9. [Write the templates and styling](#9-write-the-templates-and-styling)
10. [Run it for the first time](#10-run-it-for-the-first-time)
11. [Add sample data](#11-add-sample-data)
12. [Add tests](#12-add-tests)
13. [Add the production HTTPS server, certificates and backups](#13-add-the-production-https-server-certificates-and-backups)
14. [Add Salesforce capture (Chrome extension)](#14-add-salesforce-capture-chrome-extension)
15. [Save your work with Git](#15-save-your-work-with-git)
16. [Next steps](#16-next-steps)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Install the tools

1. **Python 3.12 or 3.13**: download the Windows installer (64-bit) from
   <https://www.python.org/downloads/windows/>. In the installer, tick
   **Add python.exe to PATH**, then click *Install Now*.
2. **Visual Studio Code**: <https://code.visualstudio.com/>.
3. **Git**: <https://git-scm.com/download/win> (accept the defaults).
4. Open VS Code, press **Ctrl+Shift+X** (Extensions), and install:
   - **Python** (by Microsoft). This also installs *Pylance* and *Python Debugger*.
   - **Jinja HTML** (by samuelcolvin). Optional; gives syntax colouring in templates.
5. Check the installs. In VS Code open a terminal with **Ctrl+`** (backtick) and run:

   ```powershell
   python --version
   git --version
   ```

   Both should print a version number. If `python` opens the Microsoft Store instead, see
   [Troubleshooting](#17-troubleshooting).

## 2. Create the project in VS Code

1. Create a folder, e.g. `C:\Projects\Casework`.
2. In VS Code: **File > Open Folder...** and pick that folder. If asked
   *"Do you trust the authors?"*, click **Yes**.
3. Turn it into a Git repository (terminal, **Ctrl+`**):

   ```powershell
   git init
   ```

## 3. Create a virtual environment

A virtual environment keeps this project's Python packages separate from everything else.

1. Press **Ctrl+Shift+P**, type **Python: Create Environment**, and press Enter.
2. Choose **Venv**, then choose your Python 3.12/3.13 install.
3. VS Code creates a `.venv` folder and selects it. The bottom-right status bar should now show
   something like `3.13.x ('.venv': venv)`.
4. Close the terminal (trash-can icon) and open a new one with **Ctrl+`**. The prompt should
   start with `(.venv)`.

   If you get *"running scripts is disabled on this system"*, run this once and open a new
   terminal:

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

> Prefer the terminal? `python -m venv .venv` then `.\.venv\Scripts\Activate.ps1`, and
> pick the interpreter with **Ctrl+Shift+P > Python: Select Interpreter**.

## 4. Install the dependencies

Create a file in the project root: click the **New File** icon in the Explorer (or
**Ctrl+N** then **Ctrl+S**) and name it as shown.


#### `requirements.txt`

The libraries the app uses:
- **Flask**: the web framework
- **Flask-SQLAlchemy**: saves cases to a SQLite database file
- **cheroot**: production web server with HTTPS support (used on the server)
- **cryptography**: creates and converts HTTPS certificates
- **pytest**: runs the automated tests

```text
Flask>=3.0,<4
Flask-SQLAlchemy>=3.1,<4
cheroot>=10,<12
cryptography>=42
pytest>=8
```

Install them in the terminal (the prompt must show `(.venv)`):

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Create the folder structure

This is what you're building:

```text
Casework/
├── .vscode/                 VS Code run/debug and test settings
├── casework/                the application package
│   ├── __init__.py          creates the app (the "app factory")
│   ├── models.py            database tables: Case and Entry
│   ├── entry_types.py       definitions of the tabs and their form fields
│   ├── reports.py           builds the swarm / structured investigation reports
│   ├── routes.py            the web pages and form handling
│   ├── static/
│   │   ├── style.css
│   │   └── vendor/          Bootstrap (downloaded in step 9)
│   └── templates/           HTML pages (Jinja templates)
├── tests/                   automated tests
├── run.py                   starts the development server
├── serve.py                 starts the production (HTTPS) server
├── seed.py                  loads sample cases
├── tls_cert.py              creates / converts HTTPS certificates
├── backup.py                backs up the database
├── pytest.ini
├── requirements.txt
└── .gitignore
```

Create the folders in one go from the terminal:

```powershell
New-Item -ItemType Directory -Force casework\templates, casework\static, tests, .vscode | Out-Null
```

Then add the `.gitignore` so Git skips generated files, the database and certificates:


#### `.gitignore`

`instance/` holds your database and `certs/` your private key; neither should go into Git.

```gitignore
__pycache__/
*.pyc
.venv/
venv/
instance/
.pytest_cache/
*.db
backups/
certs/
```

## 6. Write the data layer


#### `casework/models.py`

The two database tables.

- **`Case`** holds case number, title, customer, product, version, operating system, severity,
  status, opened/closed dates, and the narrative fields that feed the reports (problem
  description, business impact, current status, next steps, help needed).
- **`Entry`** is one item of work logged against a case. Its `entry_type` decides which tab it
  appears on (initial response, scoping, troubleshooting, meeting, note).
- `age_days` counts days since the case was opened, and `swarm_due` / `investigation_due`
  compare it with the 5- and 15-day thresholds.
- `day_number()` turns a date into "Day N" of the case, used in the day-by-day logs.

```python
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
    imported_items = db.relationship("ImportedItem", cascade="all, delete-orphan", lazy="select")

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


class ImportBatch(db.Model):
    """A case captured by the Chrome extension, waiting for review."""

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(32), unique=True, nullable=False, index=True)
    case_number = db.Column(db.String(64))
    payload = db.Column(db.Text, nullable=False)  # JSON from the extension
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    applied_at = db.Column(db.DateTime)
    case_id = db.Column(db.Integer, db.ForeignKey("case.id", ondelete="SET NULL"))


class ImportedItem(db.Model):
    """Remembers which Salesforce feed items were already imported into a case."""

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("case.id"), nullable=False, index=True)
    key = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    __table_args__ = (db.UniqueConstraint("case_id", "key"),)
```

#### `casework/entry_types.py`

Describes each tab on the case page and the form fields it needs. The add/edit forms
and their validation are generated from this, so adding a field to a tab means changing only
this file (plus a column in `models.py` if it's new). It also holds the "standard scoping
questions" list.

```python
"""Definitions of the work-log tabs on a case.

Each entry type maps to a tab on the case page. `fields` drives both the add/edit
forms and validation: (column, label, widget, required, placeholder).
"""

ENTRY_TYPES = {
    "initial_response": {
        "label": "Initial Response",
        "singular": "initial response",
        "fields": [
            ("occurred_at", "Date / time sent", "datetime", True, ""),
            ("title", "Subject", "text", False, "e.g. Initial contact - acknowledging the issue"),
            ("body", "Initial response", "textarea", True, "What you sent / discussed in the first contact"),
        ],
    },
    "scoping": {
        "label": "Scoping Q&A",
        "singular": "scoping question",
        "fields": [
            ("occurred_at", "Asked on", "datetime", True, ""),
            ("question", "Scoping question", "textarea", True, "e.g. When did the issue start?"),
            ("response", "Customer response", "textarea", False, "Leave empty if still awaiting an answer"),
        ],
    },
    "troubleshooting": {
        "label": "Troubleshooting",
        "singular": "troubleshooting session",
        "fields": [
            ("occurred_at", "Session date / time", "datetime", True, ""),
            ("title", "Session title", "text", True, "e.g. Remote session - reviewed event logs"),
            ("duration_minutes", "Duration (minutes)", "number", False, "60"),
            ("body", "Actions taken / steps performed", "textarea", True, "Step-by-step what was done"),
            ("findings", "Findings / results", "textarea", False, "What you observed, errors, data collected"),
            ("next_steps", "Next steps", "textarea", False, "What follows from this session"),
        ],
    },
    "meeting": {
        "label": "Meeting Summaries",
        "singular": "meeting summary",
        "fields": [
            ("occurred_at", "Meeting date / time", "datetime", True, ""),
            ("title", "Meeting title", "text", True, "e.g. Status call with customer"),
            ("attendees", "Attendees", "text", False, "Names / roles"),
            ("body", "Meeting summary", "textarea", True, "Key discussion points and decisions"),
            ("action_items", "Action items", "textarea", False, "One per line, include owner"),
        ],
    },
    "note": {
        "label": "Other Notes",
        "singular": "note",
        "fields": [
            ("occurred_at", "Date / time", "datetime", True, ""),
            ("title", "Title", "text", True, ""),
            ("body", "Note", "textarea", True, "Anything else important for this case"),
        ],
    },
}

STANDARD_SCOPING_QUESTIONS = [
    "What is the exact problem / symptom, and what is the expected behaviour?",
    "When did the issue start, and has it ever worked correctly?",
    "What changed recently (patches, upgrades, configuration, network, infrastructure)?",
    "How many users / systems are affected, and is it all or a subset?",
    "Is the issue reproducible? What are the exact steps to reproduce?",
    "What error messages, codes or screenshots are available?",
    "What is the business impact, and is there a workaround in place?",
    "What logs / diagnostic data have already been collected?",
]
```

#### `casework/__init__.py`

The **app factory**. `create_app()` builds the Flask app, reads settings from environment
variables (database location, the 5/15-day thresholds, optional login), creates the database
tables on first run, and registers the pages from `routes.py`. The optional login at the bottom
only switches on when `CASEWORK_USERNAME` and `CASEWORK_PASSWORD` are set.

```python
import os

from flask import Flask

from .models import db


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CASEWORK_SECRET_KEY", "dev-change-me"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "CASEWORK_DATABASE_URL",
            "sqlite:///" + os.path.join(app.instance_path, "casework.db"),
        ),
        SWARM_AGE_DAYS=int(os.environ.get("CASEWORK_SWARM_AGE_DAYS", 5)),
        STRUCTURED_INVESTIGATION_AGE_DAYS=int(os.environ.get("CASEWORK_SI_AGE_DAYS", 15)),
    )
    if test_config:
        app.config.update(test_config)

    app.config.setdefault("CASEWORK_USERNAME", os.environ.get("CASEWORK_USERNAME"))
    app.config.setdefault("CASEWORK_PASSWORD", os.environ.get("CASEWORK_PASSWORD"))
    app.config.setdefault("CASEWORK_API_TOKEN", os.environ.get("CASEWORK_API_TOKEN"))
    app.config.setdefault("MAX_CONTENT_LENGTH", 20 * 1024 * 1024)

    db.init_app(app)
    _install_basic_auth(app)

    from . import routes

    from . import imports

    app.register_blueprint(routes.bp)
    app.register_blueprint(imports.bp)
    routes.register_template_helpers(app)

    with app.app_context():
        db.create_all()

    return app


def _install_basic_auth(app):
    """Require a username/password for every page when CASEWORK_USERNAME and
    CASEWORK_PASSWORD are set. Off when they are not set (local single-user use)."""
    import hmac

    from flask import Response, request

    @app.before_request
    def _require_login():
        user, pwd = app.config.get("CASEWORK_USERNAME"), app.config.get("CASEWORK_PASSWORD")
        if not (user and pwd) or request.path.startswith("/api/"):
            return None  # /api/ uses CASEWORK_API_TOKEN instead (see imports.py)
        auth = request.authorization
        if (auth and auth.type == "basic"
                and hmac.compare_digest((auth.username or "").encode(), user.encode())
                and hmac.compare_digest((auth.password or "").encode(), pwd.encode())):
            return None
        return Response("Login required.", 401, {"WWW-Authenticate": 'Basic realm="Casework"'})
```

## 7. Write the report generator


#### `casework/reports.py`

Builds the two reports as Markdown text from everything logged on the case:

- **`build_swarm_report`** (5+ days): case summary, problem, impact, what you need from the
  swarm, initial response, scoping Q&A, every troubleshooting session, meetings, notes, a
  day-by-day activity log, current status, next steps and gaps.
- **`build_structured_investigation_report`** (15+ days): adds an executive summary,
  escalation history, a timeline table, consolidated key findings and action items.
- **`readiness_gaps`** lists what's missing (no business impact, unanswered scoping questions,
  no recent troubleshooting...). It's shown on the case page and in both reports.

```python
"""Build Swarm (day 5) and Structured Investigation (day 15) write-ups as Markdown.

Everything logged on the case is compiled into one document so it can be pasted
into a swarm request / investigation template or downloaded as a .md file.
"""

from collections import OrderedDict
from datetime import datetime, timedelta

from flask import current_app

from .entry_types import ENTRY_TYPES

REPORT_KINDS = {
    "swarm": "Swarm Request",
    "structured_investigation": "Structured Investigation",
}

NOT_PROVIDED = "_Not provided yet._"


# --------------------------------------------------------------------------- helpers

def _fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def _text(value):
    value = (value or "").strip()
    return value if value else NOT_PROVIDED


def _quote(value):
    """Render multi-line free text as an indented block that survives Markdown."""
    value = (value or "").strip()
    if not value:
        return NOT_PROVIDED
    return "\n".join("> " + line if line.strip() else ">" for line in value.splitlines())


def _cell(value):
    return (value or "").replace("|", "\\|").replace("\n", " ").strip() or "-"


def _lines(value):
    return [ln.strip(" -*\t") for ln in (value or "").splitlines() if ln.strip(" -*\t")]


def _fmt_minutes(minutes):
    if not minutes:
        return "0m"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _details_table(case):
    rows = [
        ("Case number", case.case_number),
        ("Title", case.title),
        ("Customer", case.customer),
        ("Product", case.product),
        ("Version", case.version),
        ("Operating system", case.operating_system),
        ("Severity", case.severity),
        ("Status", case.status),
        ("Opened", case.opened_on.isoformat()),
        ("Case age", f"{case.age_days} days"),
    ]
    out = ["| Field | Value |", "|---|---|"]
    out += [f"| {k} | {_cell(v)} |" for k, v in rows]
    return "\n".join(out)


def _section_initial(case):
    items = case.entries_of("initial_response")
    if not items:
        return NOT_PROVIDED
    out = []
    for e in items:
        head = f"**{_fmt_dt(e.occurred_at)}** (Day {case.day_number(e.occurred_at)})"
        if e.title:
            head += f" - {e.title}"
        out += [head, "", _quote(e.body), ""]
    return "\n".join(out).rstrip()


def _section_scoping(case):
    items = case.entries_of("scoping")
    if not items:
        return NOT_PROVIDED
    out = []
    for i, e in enumerate(items, 1):
        out.append(f"{i}. **Q:** {(e.question or '').strip()}")
        resp = (e.response or "").strip()
        if resp:
            resp_lines = resp.splitlines()
            out.append(f"   **A:** {resp_lines[0]}")
            out += [f"   {ln}" for ln in resp_lines[1:]]
        else:
            out.append("   **A:** _Awaiting response_")
    return "\n".join(out)


def _section_troubleshooting(case):
    items = case.entries_of("troubleshooting")
    if not items:
        return NOT_PROVIDED
    total = sum(e.duration_minutes or 0 for e in items)
    out = [f"{len(items)} session(s), total recorded time {_fmt_minutes(total)}.", ""]
    for i, e in enumerate(items, 1):
        dur = f", {_fmt_minutes(e.duration_minutes)}" if e.duration_minutes else ""
        out += [
            f"#### Session {i}: {e.title or 'Untitled'}",
            f"*{_fmt_dt(e.occurred_at)} (Day {case.day_number(e.occurred_at)}{dur})*",
            "",
            "**Actions taken**",
            "",
            _quote(e.body),
            "",
            "**Findings / results**",
            "",
            _quote(e.findings),
            "",
            "**Next steps**",
            "",
            _quote(e.next_steps),
            "",
        ]
    return "\n".join(out).rstrip()


def _section_meetings(case):
    items = case.entries_of("meeting")
    if not items:
        return NOT_PROVIDED
    out = []
    for e in items:
        out += [
            f"#### {e.title or 'Meeting'} - {_fmt_dt(e.occurred_at)} (Day {case.day_number(e.occurred_at)})",
            f"**Attendees:** {(e.attendees or '').strip() or '-'}",
            "",
            _quote(e.body),
            "",
        ]
        actions = _lines(e.action_items)
        if actions:
            out.append("**Action items:**")
            out += [f"- [ ] {a}" for a in actions]
            out.append("")
    return "\n".join(out).rstrip()


def _section_notes(case):
    items = case.entries_of("note")
    if not items:
        return NOT_PROVIDED
    out = []
    for e in items:
        out += [f"#### {e.title or 'Note'} - {_fmt_dt(e.occurred_at)}", "", _quote(e.body), ""]
    return "\n".join(out).rstrip()


def _daily_log(case, until_day=None):
    """Group every entry by case day: Day 1 = opened date."""
    by_day = OrderedDict()
    for e in sorted(case.entries, key=lambda x: x.occurred_at):
        day = case.day_number(e.occurred_at)
        if until_day is not None and day > until_day:
            continue
        by_day.setdefault(day, []).append(e)
    if not by_day:
        return NOT_PROVIDED
    out = []
    for day, items in by_day.items():
        d = case.opened_on + timedelta(days=day - 1)
        out.append(f"**Day {day} - {d.strftime('%a %Y-%m-%d')}**")
        for e in items:
            label = ENTRY_TYPES[e.entry_type]["label"]
            out.append(f"- {e.occurred_at.strftime('%H:%M')} [{label}] {e.summary}")
        out.append("")
    return "\n".join(out).rstrip()


def _timeline_table(case):
    items = sorted(case.entries, key=lambda x: x.occurred_at)
    if not items:
        return NOT_PROVIDED
    out = ["| Day | Date / time | Type | Summary |", "|---|---|---|---|"]
    for e in items:
        out.append(
            f"| {case.day_number(e.occurred_at)} | {_fmt_dt(e.occurred_at)} | "
            f"{ENTRY_TYPES[e.entry_type]['label']} | {_cell(e.summary)} |"
        )
    return "\n".join(out)


def readiness_gaps(case):
    """Things missing from the case that a swarm / investigation reviewer will ask about."""
    gaps = []
    if not (case.problem_description or "").strip():
        gaps.append("Problem description is empty (Overview tab > Edit case).")
    if not (case.business_impact or "").strip():
        gaps.append("Business impact is not documented.")
    if not (case.version or "").strip():
        gaps.append("Product version is missing.")
    if not (case.operating_system or "").strip():
        gaps.append("Operating system is missing.")
    if not case.entries_of("initial_response"):
        gaps.append("No initial response logged.")
    scoping = case.entries_of("scoping")
    if not scoping:
        gaps.append("No scoping questions logged.")
    unanswered = [e for e in scoping if not (e.response or "").strip()]
    if unanswered:
        gaps.append(f"{len(unanswered)} scoping question(s) still awaiting a response.")
    ts = case.entries_of("troubleshooting")
    if not ts:
        gaps.append("No troubleshooting sessions logged.")
    else:
        no_findings = [e for e in ts if not (e.findings or "").strip()]
        if no_findings:
            gaps.append(f"{len(no_findings)} troubleshooting session(s) have no findings recorded.")
        last = max(e.occurred_at for e in ts)
        if not case.is_closed and datetime.now() - last > timedelta(days=3):
            gaps.append(f"No troubleshooting activity in the last {(datetime.now() - last).days} days.")
    if not (case.current_status or "").strip():
        gaps.append("Current status summary is empty.")
    if not (case.next_steps or "").strip():
        gaps.append("Next steps are not documented.")
    if not (case.help_needed or "").strip():
        gaps.append("'Help needed / ask' is empty - say what you want from the swarm / investigation.")
    return gaps


def _gaps_section(case):
    gaps = readiness_gaps(case)
    if not gaps:
        return "None identified - all key fields are populated."
    return "\n".join(f"- {g}" for g in gaps)


def _executive_summary(case):
    ts = case.entries_of("troubleshooting")
    meetings = case.entries_of("meeting")
    scoping = case.entries_of("scoping")
    answered = sum(1 for e in scoping if (e.response or "").strip())
    total = sum(e.duration_minutes or 0 for e in ts)
    env = " ".join(x for x in [case.product, case.version] if x)
    if case.operating_system:
        env += f" on {case.operating_system}"
    who = f" for {case.customer}" if case.customer else ""
    return (
        f"Case {case.case_number} (\"{case.title}\"){who} was opened on {case.opened_on.isoformat()} "
        f"and is now {case.age_days} days old with status **{case.status}**"
        f"{' and severity ' + case.severity if case.severity else ''}. "
        f"The issue affects {env or 'an unspecified environment'}. "
        f"To date, {len(ts)} troubleshooting session(s) totalling {_fmt_minutes(total)} and "
        f"{len(meetings)} meeting(s) have been held, and {answered} of {len(scoping)} "
        f"scoping question(s) have been answered. The case has exceeded the "
        f"{current_app.config['STRUCTURED_INVESTIGATION_AGE_DAYS']}-day threshold and requires a "
        f"structured investigation."
        if case.investigation_due
        else
        f"Case {case.case_number} (\"{case.title}\"){who} was opened on {case.opened_on.isoformat()} "
        f"and is {case.age_days} days old with status **{case.status}**. "
        f"Environment: {env or 'unspecified'}. "
        f"{len(ts)} troubleshooting session(s) ({_fmt_minutes(total)}) and {len(meetings)} meeting(s) logged; "
        f"{answered} of {len(scoping)} scoping question(s) answered."
    )


def _all_findings(case):
    out = []
    for e in case.entries_of("troubleshooting"):
        for ln in _lines(e.findings):
            out.append(f"- Day {case.day_number(e.occurred_at)} ({e.title or 'session'}): {ln}")
    return "\n".join(out) if out else NOT_PROVIDED


def _all_action_items(case):
    out = []
    for e in case.entries_of("meeting"):
        for ln in _lines(e.action_items):
            out.append(f"- [ ] {ln} _(from {e.title or 'meeting'}, {e.occurred_at:%Y-%m-%d})_")
    return "\n".join(out) if out else NOT_PROVIDED


# --------------------------------------------------------------------------- reports

def build_swarm_report(case):
    cfg = current_app.config
    parts = [
        f"# Swarm Request - Case {case.case_number}",
        "",
        f"**{case.title}**  ",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} | Case age **{case.age_days} days** "
        f"(swarm threshold: {cfg['SWARM_AGE_DAYS']} days)",
        "",
        "## 1. Case Summary",
        _details_table(case),
        "",
        "## 2. Problem Description",
        _quote(case.problem_description),
        "",
        "## 3. Business Impact",
        _quote(case.business_impact),
        "",
        "## 4. What I Need From the Swarm",
        _quote(case.help_needed),
        "",
        "## 5. Initial Response",
        _section_initial(case),
        "",
        "## 6. Scoping Questions & Responses",
        _section_scoping(case),
        "",
        "## 7. Troubleshooting Performed",
        _section_troubleshooting(case),
        "",
        "## 8. Meeting Summaries",
        _section_meetings(case),
        "",
        "## 9. Other Important Notes",
        _section_notes(case),
        "",
        "## 10. Day-by-Day Activity Log",
        _daily_log(case),
        "",
        "## 11. Current Status",
        _quote(case.current_status),
        "",
        "## 12. Planned Next Steps",
        _quote(case.next_steps),
        "",
        "## 13. Gaps / Open Items",
        _gaps_section(case),
        "",
    ]
    return "\n".join(parts)


def build_structured_investigation_report(case):
    cfg = current_app.config
    ts = case.entries_of("troubleshooting")
    swarm_day = case.opened_on + timedelta(days=cfg["SWARM_AGE_DAYS"])
    escalation = [
        f"- Case opened: {case.opened_on.isoformat()}",
        f"- Swarm threshold ({cfg['SWARM_AGE_DAYS']} days) reached: {swarm_day.isoformat()}",
        f"- Structured investigation threshold ({cfg['STRUCTURED_INVESTIGATION_AGE_DAYS']} days) reached: "
        f"{(case.opened_on + timedelta(days=cfg['STRUCTURED_INVESTIGATION_AGE_DAYS'])).isoformat()}",
    ]
    swarm_mentions = [
        e for e in case.entries
        if "swarm" in " ".join(filter(None, [e.title, e.body])).lower()
    ]
    if swarm_mentions:
        escalation.append("- Swarm-related activity logged:")
        escalation += [f"  - {_fmt_dt(e.occurred_at)}: {e.summary}" for e in swarm_mentions]

    parts = [
        f"# Structured Investigation - Case {case.case_number}",
        "",
        f"**{case.title}**  ",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} | Case age **{case.age_days} days** "
        f"(investigation threshold: {cfg['STRUCTURED_INVESTIGATION_AGE_DAYS']} days)",
        "",
        "## 1. Executive Summary",
        _executive_summary(case),
        "",
        "## 2. Case Details",
        _details_table(case),
        "",
        "## 3. Problem Statement",
        "### Description",
        _quote(case.problem_description),
        "",
        "### Business Impact",
        _quote(case.business_impact),
        "",
        "## 4. Environment",
        f"- **Product:** {_text(case.product)}",
        f"- **Version:** {_text(case.version)}",
        f"- **Operating system:** {_text(case.operating_system)}",
        "",
        "## 5. Escalation History",
        "\n".join(escalation),
        "",
        "## 6. Chronological Timeline",
        _timeline_table(case),
        "",
        "## 7. Initial Response",
        _section_initial(case),
        "",
        "## 8. Scoping Summary",
        _section_scoping(case),
        "",
        "## 9. Investigation Work Completed",
        _section_troubleshooting(case),
        "",
        "## 10. Key Findings (consolidated)",
        _all_findings(case),
        "",
        "## 11. Meetings & Decisions",
        _section_meetings(case),
        "",
        "### Consolidated Action Items",
        _all_action_items(case),
        "",
        "## 12. Additional Notes",
        _section_notes(case),
        "",
        "## 13. Day-by-Day Activity Log",
        _daily_log(case),
        "",
        "## 14. Gaps & Open Questions",
        _gaps_section(case),
        "",
        "## 15. Current Status",
        _quote(case.current_status),
        "",
        "## 16. Next Steps",
        _quote(case.next_steps),
        "",
        "## 17. Investigation Ask",
        _quote(case.help_needed),
        "",
        "---",
        f"_Effort to date: {len(ts)} troubleshooting session(s), "
        f"{_fmt_minutes(sum(e.duration_minutes or 0 for e in ts))} recorded._",
        "",
    ]
    return "\n".join(parts)


def build_report(case, kind):
    if kind == "swarm":
        return build_swarm_report(case)
    if kind == "structured_investigation":
        return build_structured_investigation_report(case)
    raise ValueError(f"Unknown report kind: {kind}")
```

## 8. Write the web pages (routes)


#### `casework/routes.py`

Every URL in the app and what it does:

| URL | Page |
|---|---|
| `/` | Dashboard: case list, search, filters, swarm/SI counts |
| `/cases/new`, `/cases/<id>/edit` | Create / edit a case |
| `/cases/<id>` | Case page with all the tabs |
| `/cases/<id>/entries/<type>` | Add an entry to a tab (form POST) |
| `/entries/<id>/edit`, `/entries/<id>/delete` | Edit / delete an entry |
| `/cases/<id>/scoping/standard` | Add the standard scoping questions |
| `/cases/<id>/report/swarm` or `.../structured_investigation` | View the report; add `?download=1` to download it |

After adding an entry, the page redirects back to the same tab using a `#tab-...` anchor.

```python
import re
from datetime import date, datetime

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import or_

from .entry_types import ENTRY_TYPES, STANDARD_SCOPING_QUESTIONS
from .models import CLOSED_STATUSES, SEVERITIES, STATUSES, Case, Entry, db
from .reports import REPORT_KINDS, build_report, readiness_gaps

bp = Blueprint("main", __name__)

CASE_TEXT_FIELDS = [
    "case_number", "title", "customer", "product", "version", "operating_system",
    "severity", "status", "problem_description", "business_impact",
    "current_status", "next_steps", "help_needed",
]
CASE_REQUIRED = {"case_number": "Case number", "title": "Title", "product": "Product"}


def register_template_helpers(app):
    @app.template_filter("dt")
    def _dt(value, fmt="%Y-%m-%d %H:%M"):
        return value.strftime(fmt) if value else ""

    @app.context_processor
    def _inject():
        return {
            "ENTRY_TYPES": ENTRY_TYPES,
            "REPORT_KINDS": REPORT_KINDS,
            "SWARM_DAYS": current_app.config["SWARM_AGE_DAYS"],
            "SI_DAYS": current_app.config["STRUCTURED_INVESTIGATION_AGE_DAYS"],
            "now": datetime.now(),
        }


# --------------------------------------------------------------------------- parsing

def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except ValueError:
        return None


def _parse_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _apply_case_form(case, form):
    errors = []
    for field in CASE_TEXT_FIELDS:
        setattr(case, field, (form.get(field) or "").strip() or None)
    for field, label in CASE_REQUIRED.items():
        if not getattr(case, field):
            errors.append(f"{label} is required.")
    if case.status not in STATUSES:
        case.status = "New"

    opened = _parse_date(form.get("opened_on"))
    if not opened:
        errors.append("Opened date is required (YYYY-MM-DD).")
    else:
        case.opened_on = opened
    closed_raw = form.get("closed_on")
    case.closed_on = _parse_date(closed_raw)
    if closed_raw and not case.closed_on:
        errors.append("Closed date is invalid.")
    if case.status in CLOSED_STATUSES and not case.closed_on:
        case.closed_on = date.today()
    if case.closed_on and opened and case.closed_on < opened:
        errors.append("Closed date cannot be before the opened date.")

    if case.case_number:
        with db.session.no_autoflush:
            clash = Case.query.filter(Case.case_number == case.case_number,
                                      Case.id != case.id).first()
        if clash:
            errors.append(f"Case number {case.case_number} already exists.")
    return errors


def _apply_entry_form(entry, form):
    errors = []
    for name, label, widget, required, _ in ENTRY_TYPES[entry.entry_type]["fields"]:
        raw = (form.get(name) or "").strip()
        if widget == "datetime":
            value = _parse_datetime(raw)
            if raw and value is None:
                errors.append(f"{label} is not a valid date/time.")
            value = value or datetime.now()
        elif widget == "number":
            if raw:
                try:
                    value = int(raw)
                    if value < 0:
                        raise ValueError
                except ValueError:
                    errors.append(f"{label} must be a whole, non-negative number.")
                    value = None
            else:
                value = None
        else:
            value = raw or None
        if required and value in (None, ""):
            errors.append(f"{label} is required.")
        setattr(entry, name, value)
    return errors


def _tab_anchor(entry_type):
    return "#tab-" + entry_type.replace("_", "-")


def _case_or_404(case_id):
    return db.session.get(Case, case_id) or abort(404)


# --------------------------------------------------------------------------- dashboard

@bp.route("/")
def dashboard():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or "open"
    query = Case.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Case.case_number.ilike(like), Case.title.ilike(like), Case.customer.ilike(like),
            Case.product.ilike(like), Case.version.ilike(like), Case.operating_system.ilike(like),
        ))
    if status == "open":
        query = query.filter(Case.status.notin_(CLOSED_STATUSES))
    elif status == "closed":
        query = query.filter(Case.status.in_(CLOSED_STATUSES))
    elif status in STATUSES:
        query = query.filter(Case.status == status)
    cases = query.order_by(Case.opened_on.asc()).all()

    open_cases = Case.query.filter(Case.status.notin_(CLOSED_STATUSES)).all()
    stats = {
        "open": len(open_cases),
        "swarm": sum(1 for c in open_cases if c.escalation_stage == "swarm"),
        "si": sum(1 for c in open_cases if c.escalation_stage == "structured_investigation"),
    }
    return render_template("dashboard.html", cases=cases, q=q, status=status,
                           statuses=STATUSES, stats=stats)


# --------------------------------------------------------------------------- cases

@bp.route("/cases/new", methods=["GET", "POST"])
def case_new():
    case = Case(status="New", opened_on=date.today())
    if request.method == "POST":
        errors = _apply_case_form(case, request.form)
        if not errors:
            db.session.add(case)
            db.session.commit()
            flash(f"Case {case.case_number} created.", "success")
            return redirect(url_for("main.case_detail", case_id=case.id))
        for e in errors:
            flash(e, "danger")
    return render_template("case_form.html", case=case, statuses=STATUSES,
                           severities=SEVERITIES, is_new=True)


@bp.route("/cases/<int:case_id>")
def case_detail(case_id):
    case = _case_or_404(case_id)
    tabs = (
        [("overview", "Overview", None)]
        + [(k.replace("_", "-"), v["label"], len(case.entries_of(k))) for k, v in ENTRY_TYPES.items()]
        + [("timeline", "Timeline", len(case.entries)), ("escalation", "Swarm / Investigation", None)]
    )
    return render_template(
        "case_detail.html", case=case, gaps=readiness_gaps(case), tabs=tabs,
        timeline=sorted(case.entries, key=lambda e: e.occurred_at, reverse=True),
    )


@bp.route("/cases/<int:case_id>/edit", methods=["GET", "POST"])
def case_edit(case_id):
    case = _case_or_404(case_id)
    if request.method == "POST":
        errors = _apply_case_form(case, request.form)
        if not errors:
            db.session.commit()
            flash("Case updated.", "success")
            return redirect(url_for("main.case_detail", case_id=case.id))
        db.session.rollback()
        for e in errors:
            flash(e, "danger")
        # re-populate the form with what the user typed
        case = Case(id=case_id, opened_on=_parse_date(request.form.get("opened_on")) or date.today(),
                    closed_on=_parse_date(request.form.get("closed_on")),
                    **{f: request.form.get(f) for f in CASE_TEXT_FIELDS})
    return render_template("case_form.html", case=case, statuses=STATUSES,
                           severities=SEVERITIES, is_new=False)


@bp.route("/cases/<int:case_id>/delete", methods=["POST"])
def case_delete(case_id):
    case = _case_or_404(case_id)
    number = case.case_number
    db.session.delete(case)
    db.session.commit()
    flash(f"Case {number} deleted.", "info")
    return redirect(url_for("main.dashboard"))


# --------------------------------------------------------------------------- entries

@bp.route("/cases/<int:case_id>/entries/<entry_type>", methods=["POST"])
def entry_add(case_id, entry_type):
    case = _case_or_404(case_id)
    if entry_type not in ENTRY_TYPES:
        abort(404)
    entry = Entry(case=case, entry_type=entry_type)
    errors = _apply_entry_form(entry, request.form)
    if errors:
        db.session.rollback()
        for e in errors:
            flash(e, "danger")
    else:
        db.session.add(entry)
        db.session.commit()
        flash(f"Added {ENTRY_TYPES[entry_type]['singular']}.", "success")
    return redirect(url_for("main.case_detail", case_id=case.id) + _tab_anchor(entry_type))


@bp.route("/cases/<int:case_id>/scoping/standard", methods=["POST"])
def scoping_standard(case_id):
    case = _case_or_404(case_id)
    existing = {(e.question or "").strip() for e in case.entries_of("scoping")}
    added = 0
    for q in STANDARD_SCOPING_QUESTIONS:
        if q not in existing:
            db.session.add(Entry(case=case, entry_type="scoping", question=q, occurred_at=datetime.now()))
            added += 1
    db.session.commit()
    flash(f"Added {added} standard scoping question(s)." if added
          else "Standard scoping questions are already on this case.", "info")
    return redirect(url_for("main.case_detail", case_id=case.id) + _tab_anchor("scoping"))


@bp.route("/entries/<int:entry_id>/edit", methods=["GET", "POST"])
def entry_edit(entry_id):
    entry = db.session.get(Entry, entry_id) or abort(404)
    if request.method == "POST":
        errors = _apply_entry_form(entry, request.form)
        if not errors:
            db.session.commit()
            flash("Entry updated.", "success")
            return redirect(url_for("main.case_detail", case_id=entry.case_id) + _tab_anchor(entry.entry_type))
        for e in errors:
            flash(e, "danger")
    return render_template("entry_form.html", entry=entry, case=entry.case,
                           spec=ENTRY_TYPES[entry.entry_type])


@bp.route("/entries/<int:entry_id>/delete", methods=["POST"])
def entry_delete(entry_id):
    entry = db.session.get(Entry, entry_id) or abort(404)
    case_id, entry_type = entry.case_id, entry.entry_type
    db.session.delete(entry)
    db.session.commit()
    flash("Entry deleted.", "info")
    return redirect(url_for("main.case_detail", case_id=case_id) + _tab_anchor(entry_type))


# --------------------------------------------------------------------------- reports

@bp.route("/cases/<int:case_id>/report/<kind>")
def report(case_id, kind):
    case = _case_or_404(case_id)
    if kind not in REPORT_KINDS:
        abort(404)
    markdown = build_report(case, kind)
    if request.args.get("download"):
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", case.case_number)
        return Response(
            markdown,
            mimetype="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{safe}_{kind}.md"'},
        )
    due = case.swarm_due if kind == "swarm" else case.investigation_due
    return render_template("report.html", case=case, kind=kind, title=REPORT_KINDS[kind],
                           markdown=markdown, due=due, gaps=readiness_gaps(case))
```

#### `run.py`

Starts the development server with auto-reload. Use it on your PC while building.

```python
from casework import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
```

## 9. Write the templates and styling

Templates are HTML with Jinja placeholders (`{{ ... }}` and `{% ... %}`) that Flask fills in.


#### `casework/templates/base.html`

The layout every page shares: navigation bar, flash messages, and the Bootstrap CSS/JS.

```jinja
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Casework{% endblock %} · Casework</title>
  <link href="{{ url_for('static', filename='vendor/bootstrap/bootstrap.min.css') }}" rel="stylesheet">
  <link href="{{ url_for('static', filename='vendor/bootstrap-icons/bootstrap-icons.min.css') }}" rel="stylesheet">
  <link href="{{ url_for('static', filename='style.css') }}" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand navbar-dark bg-dark mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('main.dashboard') }}"><i class="bi bi-briefcase"></i> Casework</a>
    <div class="navbar-nav">
      <a class="nav-link" href="{{ url_for('main.dashboard') }}">Dashboard</a>
      <a class="nav-link" href="{{ url_for('main.case_new') }}"><i class="bi bi-plus-circle"></i> New case</a>
    </div>
  </div>
</nav>
<main class="container-fluid px-4 pb-5">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
        {{ message }}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
      </div>
    {% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</main>
<script src="{{ url_for('static', filename='vendor/bootstrap/bootstrap.bundle.min.js') }}"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

#### `casework/templates/_macros.html`

Reusable pieces: the coloured age badge (green, yellow = swarm, red = structured
investigation), the form fields generated from `entry_types.py`, and a labelled text block.

```jinja
{% macro age_badge(case) -%}
  {%- if case.is_closed -%}
    <span class="badge text-bg-secondary">{{ case.age_days }}d</span>
  {%- elif case.escalation_stage == 'structured_investigation' -%}
    <span class="badge text-bg-danger" title="Structured investigation due">{{ case.age_days }}d · SI</span>
  {%- elif case.escalation_stage == 'swarm' -%}
    <span class="badge text-bg-warning" title="Swarm due">{{ case.age_days }}d · Swarm</span>
  {%- else -%}
    <span class="badge text-bg-success">{{ case.age_days }}d</span>
  {%- endif -%}
{%- endmacro %}

{% macro entry_fields(spec, entry=None, prefix='') -%}
  {% for name, label, widget, required, placeholder in spec.fields %}
    {% set fid = prefix ~ name %}
    {% set value = entry[name] if entry else None %}
    <div class="mb-3 {% if widget in ('datetime', 'number') %}d-inline-block me-3{% endif %}">
      <label class="form-label fw-semibold" for="{{ fid }}">{{ label }}{% if required %} <span class="text-danger">*</span>{% endif %}</label>
      {% if widget == 'textarea' %}
        <textarea class="form-control" id="{{ fid }}" name="{{ name }}" rows="4"
                  placeholder="{{ placeholder }}" {% if required %}required{% endif %}>{{ value or '' }}</textarea>
      {% elif widget == 'datetime' %}
        <input class="form-control" type="datetime-local" id="{{ fid }}" name="{{ name }}"
               value="{{ (value or now) | dt('%Y-%m-%dT%H:%M') }}" {% if required %}required{% endif %}>
      {% elif widget == 'number' %}
        <input class="form-control" type="number" min="0" id="{{ fid }}" name="{{ name }}"
               value="{{ value if value is not none else '' }}" placeholder="{{ placeholder }}">
      {% else %}
        <input class="form-control" type="text" id="{{ fid }}" name="{{ name }}"
               value="{{ value or '' }}" placeholder="{{ placeholder }}" {% if required %}required{% endif %}>
      {% endif %}
    </div>
  {% endfor %}
{%- endmacro %}

{% macro text_block(label, value) -%}
  {% if value %}
    <div class="mb-2">
      <div class="small text-uppercase text-body-secondary fw-semibold">{{ label }}</div>
      <div class="prewrap">{{ value }}</div>
    </div>
  {% endif %}
{%- endmacro %}
```

#### `casework/templates/dashboard.html`

The home page: summary cards, search box, status filter and the case table.

```jinja
{% extends "base.html" %}
{% from "_macros.html" import age_badge %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<div class="row g-3 mb-4">
  <div class="col-sm-4">
    <div class="card stat-card border-success"><div class="card-body">
      <div class="text-body-secondary small">Open cases</div><div class="fs-2 fw-bold">{{ stats.open }}</div>
    </div></div>
  </div>
  <div class="col-sm-4">
    <div class="card stat-card border-warning"><div class="card-body">
      <div class="text-body-secondary small">Swarm due ({{ SWARM_DAYS }}+ days)</div><div class="fs-2 fw-bold">{{ stats.swarm }}</div>
    </div></div>
  </div>
  <div class="col-sm-4">
    <div class="card stat-card border-danger"><div class="card-body">
      <div class="text-body-secondary small">Structured investigation due ({{ SI_DAYS }}+ days)</div><div class="fs-2 fw-bold">{{ stats.si }}</div>
    </div></div>
  </div>
</div>

<form class="row g-2 mb-3" method="get">
  <div class="col-md-6">
    <input class="form-control" name="q" value="{{ q }}" placeholder="Search case #, title, customer, product, version, OS">
  </div>
  <div class="col-md-3">
    <select class="form-select" name="status" onchange="this.form.submit()">
      <option value="open" {% if status == 'open' %}selected{% endif %}>All open</option>
      <option value="all" {% if status == 'all' %}selected{% endif %}>All cases</option>
      <option value="closed" {% if status == 'closed' %}selected{% endif %}>Resolved / closed</option>
      {% for s in statuses %}<option {% if status == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
    </select>
  </div>
  <div class="col-md-3 d-flex gap-2">
    <button class="btn btn-outline-primary"><i class="bi bi-search"></i> Search</button>
    <a class="btn btn-primary ms-auto" href="{{ url_for('main.case_new') }}"><i class="bi bi-plus-lg"></i> New case</a>
  </div>
</form>

{% if cases %}
<div class="table-responsive">
<table class="table table-hover align-middle">
  <thead class="table-light">
    <tr><th>Case #</th><th>Title</th><th>Product</th><th>Version</th><th>OS</th><th>Severity</th><th>Status</th><th>Opened</th><th>Age</th><th>Logged</th><th></th></tr>
  </thead>
  <tbody>
  {% for c in cases %}
    <tr>
      <td><a class="fw-semibold" href="{{ url_for('main.case_detail', case_id=c.id) }}">{{ c.case_number }}</a></td>
      <td>{{ c.title }}{% if c.customer %}<div class="small text-body-secondary">{{ c.customer }}</div>{% endif %}</td>
      <td>{{ c.product }}</td>
      <td>{{ c.version or '' }}</td>
      <td>{{ c.operating_system or '' }}</td>
      <td>{{ c.severity or '' }}</td>
      <td>{{ c.status }}</td>
      <td class="text-nowrap">{{ c.opened_on }}</td>
      <td>{{ age_badge(c) }}</td>
      <td class="small text-body-secondary text-nowrap">
        {{ c.entries_of('troubleshooting')|length }} TS · {{ c.entries_of('meeting')|length }} mtg
      </td>
      <td class="text-nowrap">
        {% if not c.is_closed and c.escalation_stage == 'structured_investigation' %}
          <a class="btn btn-sm btn-danger" href="{{ url_for('main.report', case_id=c.id, kind='structured_investigation') }}">SI report</a>
        {% elif not c.is_closed and c.escalation_stage == 'swarm' %}
          <a class="btn btn-sm btn-warning" href="{{ url_for('main.report', case_id=c.id, kind='swarm') }}">Swarm report</a>
        {% endif %}
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% else %}
<div class="text-center text-body-secondary py-5">
  <i class="bi bi-inbox fs-1"></i>
  <p class="mt-2">No cases found. <a href="{{ url_for('main.case_new') }}">Create your first case</a>.</p>
</div>
{% endif %}
{% endblock %}
```

#### `casework/templates/case_form.html`

The new / edit case form: case details plus the narrative fields used by the reports.

```jinja
{% extends "base.html" %}
{% block title %}{{ 'New case' if is_new else 'Edit ' ~ case.case_number }}{% endblock %}
{% block content %}
<h1 class="h3 mb-3">{{ 'New case' if is_new else 'Edit case ' ~ case.case_number }}</h1>
<form method="post" class="card"><div class="card-body">
  <h2 class="h6 text-uppercase text-body-secondary">Case details</h2>
  <div class="row g-3 mb-4">
    <div class="col-md-3">
      <label class="form-label fw-semibold" for="case_number">Case number <span class="text-danger">*</span></label>
      <input class="form-control" id="case_number" name="case_number" value="{{ case.case_number or '' }}" required>
    </div>
    <div class="col-md-6">
      <label class="form-label fw-semibold" for="title">Title / short description <span class="text-danger">*</span></label>
      <input class="form-control" id="title" name="title" value="{{ case.title or '' }}" required>
    </div>
    <div class="col-md-3">
      <label class="form-label fw-semibold" for="customer">Customer</label>
      <input class="form-control" id="customer" name="customer" value="{{ case.customer or '' }}">
    </div>
    <div class="col-md-4">
      <label class="form-label fw-semibold" for="product">Product <span class="text-danger">*</span></label>
      <input class="form-control" id="product" name="product" value="{{ case.product or '' }}" required>
    </div>
    <div class="col-md-2">
      <label class="form-label fw-semibold" for="version">Version</label>
      <input class="form-control" id="version" name="version" value="{{ case.version or '' }}">
    </div>
    <div class="col-md-3">
      <label class="form-label fw-semibold" for="operating_system">Operating system</label>
      <input class="form-control" id="operating_system" name="operating_system" value="{{ case.operating_system or '' }}"
             placeholder="e.g. Windows Server 2022, RHEL 9.4">
    </div>
    <div class="col-md-3">
      <label class="form-label fw-semibold" for="severity">Severity</label>
      <select class="form-select" id="severity" name="severity">
        <option value="">-</option>
        {% for s in severities %}<option {% if case.severity == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label fw-semibold" for="status">Status</label>
      <select class="form-select" id="status" name="status">
        {% for s in statuses %}<option {% if case.status == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label fw-semibold" for="opened_on">Opened on <span class="text-danger">*</span></label>
      <input class="form-control" type="date" id="opened_on" name="opened_on" value="{{ case.opened_on or '' }}" required>
      <div class="form-text">Case age is counted from this date.</div>
    </div>
    <div class="col-md-3">
      <label class="form-label fw-semibold" for="closed_on">Closed on</label>
      <input class="form-control" type="date" id="closed_on" name="closed_on" value="{{ case.closed_on or '' }}">
    </div>
  </div>

  <h2 class="h6 text-uppercase text-body-secondary">Narrative <span class="text-lowercase fw-normal">(feeds the swarm / structured investigation reports)</span></h2>
  <div class="row g-3">
    {% for name, label, hint in [
      ('problem_description', 'Problem description', 'What is broken, symptoms, error messages'),
      ('business_impact', 'Business impact', 'Who / what is affected and how badly'),
      ('current_status', 'Current status', 'Where the case stands right now'),
      ('next_steps', 'Next steps', 'What you plan to do next'),
      ('help_needed', 'Help needed / ask', 'What you want from a swarm or investigation team'),
    ] %}
    <div class="col-md-6">
      <label class="form-label fw-semibold" for="{{ name }}">{{ label }}</label>
      <textarea class="form-control" id="{{ name }}" name="{{ name }}" rows="4" placeholder="{{ hint }}">{{ case[name] or '' }}</textarea>
    </div>
    {% endfor %}
  </div>
</div>
<div class="card-footer d-flex gap-2">
  <button class="btn btn-primary"><i class="bi bi-check-lg"></i> Save</button>
  <a class="btn btn-outline-secondary" href="{{ url_for('main.dashboard') if is_new else url_for('main.case_detail', case_id=case.id) }}">Cancel</a>
</div>
</form>
{% endblock %}
```

#### `casework/templates/case_detail.html`

The case page with all the tabs: Overview, Initial Response, Scoping Q&A,
Troubleshooting, Meeting Summaries, Other Notes, Timeline, and Swarm / Investigation. The script
at the bottom reopens the right tab after you add or edit something.

```jinja
{% extends "base.html" %}
{% from "_macros.html" import age_badge, entry_fields, text_block with context %}
{% block title %}{{ case.case_number }}{% endblock %}

{% macro entry_actions(e) %}
  <div class="btn-group btn-group-sm">
    <a class="btn btn-outline-secondary" href="{{ url_for('main.entry_edit', entry_id=e.id) }}" title="Edit"><i class="bi bi-pencil"></i></a>
    <form method="post" action="{{ url_for('main.entry_delete', entry_id=e.id) }}" onsubmit="return confirm('Delete this entry?')">
      <button class="btn btn-outline-danger btn-sm rounded-start-0" title="Delete"><i class="bi bi-trash"></i></button>
    </form>
  </div>
{% endmacro %}

{% macro add_form(type_key, open=False) %}
  {% set spec = ENTRY_TYPES[type_key] %}
  <details class="card mb-3 add-form" {% if open %}open{% endif %}>
    <summary class="card-header fw-semibold"><i class="bi bi-plus-circle"></i> Add {{ spec.singular }}</summary>
    <form class="card-body" method="post" action="{{ url_for('main.entry_add', case_id=case.id, entry_type=type_key) }}">
      {{ entry_fields(spec, prefix=type_key ~ '-') }}
      <div><button class="btn btn-primary"><i class="bi bi-plus-lg"></i> Add</button></div>
    </form>
  </details>
{% endmacro %}

{% block content %}
<div class="d-flex flex-wrap align-items-start gap-3 mb-3">
  <div>
    <h1 class="h3 mb-1">{{ case.case_number }} <span class="fw-normal">— {{ case.title }}</span></h1>
    <div class="text-body-secondary">
      {{ case.product }}{% if case.version %} {{ case.version }}{% endif %}
      {% if case.operating_system %} · {{ case.operating_system }}{% endif %}
      {% if case.customer %} · {{ case.customer }}{% endif %}
      · {{ case.status }} {% if case.severity %}· Sev {{ case.severity }}{% endif %}
      · opened {{ case.opened_on }} {{ age_badge(case) }}
    </div>
  </div>
  <div class="ms-auto d-flex gap-2">
    <a class="btn btn-outline-primary" href="{{ url_for('main.case_edit', case_id=case.id) }}"><i class="bi bi-pencil"></i> Edit case</a>
    <form method="post" action="{{ url_for('main.case_delete', case_id=case.id) }}"
          onsubmit="return confirm('Delete case {{ case.case_number }} and all of its notes?')">
      <button class="btn btn-outline-danger"><i class="bi bi-trash"></i></button>
    </form>
  </div>
</div>

{% if not case.is_closed and case.escalation_stage == 'structured_investigation' %}
  <div class="alert alert-danger d-flex align-items-center gap-3">
    <i class="bi bi-exclamation-octagon fs-4"></i>
    <div class="flex-grow-1">This case is <strong>{{ case.age_days }} days</strong> old ({{ SI_DAYS }}+): a <strong>structured investigation</strong> is due.</div>
    <a class="btn btn-danger" href="{{ url_for('main.report', case_id=case.id, kind='structured_investigation') }}">Build SI report</a>
  </div>
{% elif not case.is_closed and case.escalation_stage == 'swarm' %}
  <div class="alert alert-warning d-flex align-items-center gap-3">
    <i class="bi bi-people fs-4"></i>
    <div class="flex-grow-1">This case is <strong>{{ case.age_days }} days</strong> old ({{ SWARM_DAYS }}+): time to <strong>create a swarm</strong>.</div>
    <a class="btn btn-warning" href="{{ url_for('main.report', case_id=case.id, kind='swarm') }}">Build swarm report</a>
  </div>
{% endif %}

<ul class="nav nav-tabs" id="caseTabs" role="tablist">
  {% for tid, label, count in tabs %}
    <li class="nav-item" role="presentation">
      <button class="nav-link {% if loop.first %}active{% endif %}" id="btn-{{ tid }}" data-bs-toggle="tab"
              data-bs-target="#tab-{{ tid }}" type="button" role="tab">
        {{ label }}{% if count is not none %} <span class="badge rounded-pill text-bg-light border">{{ count }}</span>{% endif %}
      </button>
    </li>
  {% endfor %}
</ul>

<div class="tab-content border border-top-0 rounded-bottom p-3 bg-body">

  {# ---------------------------------------------------------------- Overview #}
  <div class="tab-pane fade show active" id="tab-overview" role="tabpanel">
    <div class="row g-4">
      <div class="col-lg-4">
        <table class="table table-sm">
          <tbody>
            <tr><th>Case number</th><td>{{ case.case_number }}</td></tr>
            <tr><th>Product</th><td>{{ case.product }}</td></tr>
            <tr><th>Version</th><td>{{ case.version or '—' }}</td></tr>
            <tr><th>Operating system</th><td>{{ case.operating_system or '—' }}</td></tr>
            <tr><th>Customer</th><td>{{ case.customer or '—' }}</td></tr>
            <tr><th>Severity</th><td>{{ case.severity or '—' }}</td></tr>
            <tr><th>Status</th><td>{{ case.status }}</td></tr>
            <tr><th>Opened</th><td>{{ case.opened_on }}</td></tr>
            {% if case.closed_on %}<tr><th>Closed</th><td>{{ case.closed_on }}</td></tr>{% endif %}
            <tr><th>Age</th><td>{{ case.age_days }} days</td></tr>
            <tr><th>Last updated</th><td>{{ case.updated_at|dt }}</td></tr>
          </tbody>
        </table>
      </div>
      <div class="col-lg-8">
        {% for label, value in [('Problem description', case.problem_description), ('Business impact', case.business_impact),
                                ('Current status', case.current_status), ('Next steps', case.next_steps),
                                ('Help needed / ask', case.help_needed)] %}
          <div class="mb-3">
            <div class="small text-uppercase text-body-secondary fw-semibold">{{ label }}</div>
            {% if value %}<div class="prewrap">{{ value }}</div>
            {% else %}<div class="text-body-tertiary fst-italic">Not filled in — <a href="{{ url_for('main.case_edit', case_id=case.id) }}">edit case</a></div>{% endif %}
          </div>
        {% endfor %}
      </div>
    </div>
  </div>

  {# ---------------------------------------------------------------- Initial response #}
  <div class="tab-pane fade" id="tab-initial-response" role="tabpanel">
    {% set items = case.entries_of('initial_response') %}
    {{ add_form('initial_response', open=not items) }}
    {% for e in items %}
      <div class="card mb-2"><div class="card-body">
        <div class="d-flex mb-2">
          <div><strong>{{ e.title or 'Initial response' }}</strong>
            <span class="text-body-secondary small ms-2">{{ e.occurred_at|dt }} · Day {{ case.day_number(e.occurred_at) }}</span></div>
          <div class="ms-auto">{{ entry_actions(e) }}</div>
        </div>
        <div class="prewrap">{{ e.body }}</div>
      </div></div>
    {% endfor %}
  </div>

  {# ---------------------------------------------------------------- Scoping #}
  <div class="tab-pane fade" id="tab-scoping" role="tabpanel">
    {% set items = case.entries_of('scoping') %}
    <div class="d-flex gap-2 mb-2">
      <form method="post" action="{{ url_for('main.scoping_standard', case_id=case.id) }}">
        <button class="btn btn-sm btn-outline-secondary"><i class="bi bi-list-check"></i> Add standard scoping questions</button>
      </form>
      {% set pending = items|rejectattr('response')|list|length %}
      {% if pending %}<span class="badge text-bg-warning align-self-center">{{ pending }} awaiting response</span>{% endif %}
    </div>
    {{ add_form('scoping') }}
    {% for e in items %}
      <div class="card mb-2 {% if not e.response %}border-warning{% endif %}"><div class="card-body">
        <div class="d-flex">
          <div class="flex-grow-1">
            <div class="fw-semibold prewrap">Q{{ loop.index }}. {{ e.question }}</div>
            {% if e.response %}<div class="prewrap mt-1"><span class="text-success fw-semibold">A:</span> {{ e.response }}</div>
            {% else %}<div class="mt-1 text-warning-emphasis fst-italic">Awaiting response</div>{% endif %}
            <div class="text-body-secondary small mt-1">{{ e.occurred_at|dt }}</div>
          </div>
          <div class="ms-2">{{ entry_actions(e) }}</div>
        </div>
      </div></div>
    {% else %}
      <p class="text-body-secondary">No scoping questions yet.</p>
    {% endfor %}
  </div>

  {# ---------------------------------------------------------------- Troubleshooting #}
  <div class="tab-pane fade" id="tab-troubleshooting" role="tabpanel">
    {% set items = case.entries_of('troubleshooting') %}
    {{ add_form('troubleshooting') }}
    {% if items %}
      <p class="small text-body-secondary">{{ items|length }} session(s), {{ items|map(attribute='duration_minutes')|select|sum }} minutes recorded.</p>
    {% endif %}
    {% for e in items|reverse %}
      <div class="card mb-2"><div class="card-body">
        <div class="d-flex mb-2">
          <div><strong>{{ e.title }}</strong>
            <span class="text-body-secondary small ms-2">{{ e.occurred_at|dt }} · Day {{ case.day_number(e.occurred_at) }}{% if e.duration_minutes %} · {{ e.duration_minutes }} min{% endif %}</span></div>
          <div class="ms-auto">{{ entry_actions(e) }}</div>
        </div>
        {{ text_block('Actions taken', e.body) }}
        {{ text_block('Findings / results', e.findings) }}
        {{ text_block('Next steps', e.next_steps) }}
      </div></div>
    {% else %}
      <p class="text-body-secondary">No troubleshooting sessions yet.</p>
    {% endfor %}
  </div>

  {# ---------------------------------------------------------------- Meetings #}
  <div class="tab-pane fade" id="tab-meeting" role="tabpanel">
    {% set items = case.entries_of('meeting') %}
    {{ add_form('meeting') }}
    {% for e in items|reverse %}
      <div class="card mb-2"><div class="card-body">
        <div class="d-flex mb-2">
          <div><strong>{{ e.title }}</strong>
            <span class="text-body-secondary small ms-2">{{ e.occurred_at|dt }} · Day {{ case.day_number(e.occurred_at) }}</span></div>
          <div class="ms-auto">{{ entry_actions(e) }}</div>
        </div>
        {{ text_block('Attendees', e.attendees) }}
        {{ text_block('Summary', e.body) }}
        {{ text_block('Action items', e.action_items) }}
      </div></div>
    {% else %}
      <p class="text-body-secondary">No meetings logged yet.</p>
    {% endfor %}
  </div>

  {# ---------------------------------------------------------------- Notes #}
  <div class="tab-pane fade" id="tab-note" role="tabpanel">
    {% set items = case.entries_of('note') %}
    {{ add_form('note') }}
    {% for e in items|reverse %}
      <div class="card mb-2"><div class="card-body">
        <div class="d-flex mb-2">
          <div><strong>{{ e.title }}</strong> <span class="text-body-secondary small ms-2">{{ e.occurred_at|dt }}</span></div>
          <div class="ms-auto">{{ entry_actions(e) }}</div>
        </div>
        <div class="prewrap">{{ e.body }}</div>
      </div></div>
    {% else %}
      <p class="text-body-secondary">No notes yet.</p>
    {% endfor %}
  </div>

  {# ---------------------------------------------------------------- Timeline #}
  <div class="tab-pane fade" id="tab-timeline" role="tabpanel">
    {% if timeline %}
    <table class="table table-sm align-middle">
      <thead><tr><th>Day</th><th>When</th><th>Type</th><th>Summary</th></tr></thead>
      <tbody>
      {% for e in timeline %}
        <tr>
          <td>{{ case.day_number(e.occurred_at) }}</td>
          <td class="text-nowrap">{{ e.occurred_at|dt }}</td>
          <td><span class="badge type-{{ e.entry_type }}">{{ ENTRY_TYPES[e.entry_type].label }}</span></td>
          <td>{{ e.summary }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}
      <p class="text-body-secondary">Nothing logged yet.</p>
    {% endif %}
  </div>

  {# ---------------------------------------------------------------- Escalation #}
  <div class="tab-pane fade" id="tab-escalation" role="tabpanel">
    {% set pct = [100, (case.age_days / SI_DAYS * 100)|round|int]|min %}
    <div class="mb-1 position-relative small text-body-secondary" style="height: 1.3rem">
      <span class="position-absolute start-0">Day 0</span>
      <span class="position-absolute" style="left: {{ (SWARM_DAYS / SI_DAYS * 100)|round|int }}%">| Swarm · {{ SWARM_DAYS }}d</span>
      <span class="position-absolute end-0">SI · {{ SI_DAYS }}d</span>
    </div>
    <div class="progress mb-4" role="progressbar" style="height: 1.25rem">
      <div class="progress-bar {% if case.investigation_due %}bg-danger{% elif case.swarm_due %}bg-warning{% else %}bg-success{% endif %}"
           style="width: {{ pct }}%">{{ case.age_days }} days</div>
    </div>

    <div class="row g-3 mb-4">
      <div class="col-md-6">
        <div class="card h-100 {% if case.swarm_due %}border-warning{% endif %}"><div class="card-body">
          <h3 class="h5"><i class="bi bi-people"></i> Swarm request <small class="text-body-secondary">({{ SWARM_DAYS }}+ days)</small></h3>
          <p class="mb-3">Compiles case details, initial response, scoping Q&amp;A, all troubleshooting sessions, meetings, notes and a day-by-day log of what you've done.</p>
          {% if case.swarm_due %}<span class="badge text-bg-warning mb-2">Due</span>{% else %}<span class="badge text-bg-light border mb-2">Due in {{ SWARM_DAYS - case.age_days }} day(s)</span>{% endif %}
          <div><a class="btn btn-warning" href="{{ url_for('main.report', case_id=case.id, kind='swarm') }}">Generate swarm report</a></div>
        </div></div>
      </div>
      <div class="col-md-6">
        <div class="card h-100 {% if case.investigation_due %}border-danger{% endif %}"><div class="card-body">
          <h3 class="h5"><i class="bi bi-diagram-3"></i> Structured investigation <small class="text-body-secondary">({{ SI_DAYS }}+ days)</small></h3>
          <p class="mb-3">Formal write-up: executive summary, problem statement, environment, escalation history, timeline table, consolidated findings and action items, gaps and the ask.</p>
          {% if case.investigation_due %}<span class="badge text-bg-danger mb-2">Due</span>{% else %}<span class="badge text-bg-light border mb-2">Due in {{ SI_DAYS - case.age_days }} day(s)</span>{% endif %}
          <div><a class="btn btn-danger" href="{{ url_for('main.report', case_id=case.id, kind='structured_investigation') }}">Generate SI report</a></div>
        </div></div>
      </div>
    </div>

    <h3 class="h6 text-uppercase text-body-secondary">Readiness check</h3>
    {% if gaps %}
      <ul class="list-group">
        {% for g in gaps %}<li class="list-group-item"><i class="bi bi-exclamation-triangle text-warning"></i> {{ g }}</li>{% endfor %}
      </ul>
    {% else %}
      <div class="alert alert-success mb-0"><i class="bi bi-check-circle"></i> All key information is captured.</div>
    {% endif %}
  </div>
</div>
{% endblock %}

{% block scripts %}
<script>
  // Open the tab named in the URL hash (used after adding / editing entries) and keep the hash in sync.
  (function () {
    function show(hash) {
      var btn = hash && document.querySelector('[data-bs-target="' + hash + '"]');
      if (btn) bootstrap.Tab.getOrCreateInstance(btn).show();
    }
    show(location.hash);
    window.addEventListener('hashchange', function () { show(location.hash); });
    document.querySelectorAll('#caseTabs [data-bs-toggle="tab"]').forEach(function (btn) {
      btn.addEventListener('shown.bs.tab', function (ev) {
        history.replaceState(null, '', ev.target.getAttribute('data-bs-target'));
      });
    });
  })();
</script>
{% endblock %}
```

#### `casework/templates/entry_form.html`

The page for editing a single entry.

```jinja
{% extends "base.html" %}
{% from "_macros.html" import entry_fields with context %}
{% block title %}Edit {{ spec.singular }}{% endblock %}
{% block content %}
<h1 class="h4 mb-3">Edit {{ spec.singular }} · <a href="{{ url_for('main.case_detail', case_id=case.id) }}">{{ case.case_number }}</a></h1>
<form method="post" class="card">
  <div class="card-body">{{ entry_fields(spec, entry) }}</div>
  <div class="card-footer d-flex gap-2">
    <button class="btn btn-primary"><i class="bi bi-check-lg"></i> Save</button>
    <a class="btn btn-outline-secondary" href="{{ url_for('main.case_detail', case_id=case.id) }}#tab-{{ entry.entry_type.replace('_', '-') }}">Cancel</a>
  </div>
</form>
{% endblock %}
```

#### `casework/templates/report.html`

Shows a generated report with Copy, Download .md and Print buttons.

```jinja
{% extends "base.html" %}
{% block title %}{{ title }} · {{ case.case_number }}{% endblock %}
{% block content %}
<div class="d-flex flex-wrap align-items-center gap-2 mb-3">
  <h1 class="h4 mb-0">{{ title }} · <a href="{{ url_for('main.case_detail', case_id=case.id) }}">{{ case.case_number }}</a></h1>
  <div class="ms-auto d-flex gap-2">
    <button class="btn btn-primary" id="copyBtn"><i class="bi bi-clipboard"></i> Copy</button>
    <a class="btn btn-outline-primary" href="{{ url_for('main.report', case_id=case.id, kind=kind, download=1) }}"><i class="bi bi-download"></i> Download .md</a>
    <button class="btn btn-outline-secondary" onclick="window.print()"><i class="bi bi-printer"></i> Print</button>
  </div>
</div>

{% if not due %}
  <div class="alert alert-info">This case is {{ case.age_days }} day(s) old, so the {{ title|lower }} isn't due yet
    ({{ SWARM_DAYS if kind == 'swarm' else SI_DAYS }} days). You can still generate it early.</div>
{% endif %}
{% if gaps %}
  <details class="alert alert-warning">
    <summary><strong>{{ gaps|length }} gap(s)</strong> a reviewer is likely to ask about — fill these in for a stronger request.</summary>
    <ul class="mb-0 mt-2">{% for g in gaps %}<li>{{ g }}</li>{% endfor %}</ul>
  </details>
{% endif %}

<textarea id="report" class="form-control font-monospace report-text" rows="40" readonly>{{ markdown }}</textarea>
{% endblock %}

{% block scripts %}
<script>
  document.getElementById('copyBtn').addEventListener('click', function () {
    var ta = document.getElementById('report'), btn = this;
    var done = function () { btn.innerHTML = '<i class="bi bi-check-lg"></i> Copied'; setTimeout(function () { btn.innerHTML = '<i class="bi bi-clipboard"></i> Copy'; }, 1500); };
    if (navigator.clipboard) { navigator.clipboard.writeText(ta.value).then(done); }
    else { ta.select(); document.execCommand('copy'); done(); }
  });
</script>
{% endblock %}
```

#### `casework/static/style.css`

A few small style tweaks on top of Bootstrap, including the print layout for reports.

```css
.prewrap { white-space: pre-wrap; }
.stat-card { border-left-width: 4px !important; }
.add-form > summary { cursor: pointer; list-style: none; }
.add-form > summary::-webkit-details-marker { display: none; }
.add-form:not([open]) > summary { border-bottom: 0; }
.report-text { font-size: .85rem; min-height: 60vh; }
.nav-tabs .nav-link { white-space: nowrap; }

.badge.type-initial_response { background: #0d6efd; }
.badge.type-scoping { background: #6f42c1; }
.badge.type-troubleshooting { background: #fd7e14; }
.badge.type-meeting { background: #198754; }
.badge.type-note { background: #6c757d; }

@media print {
  nav.navbar, .btn, .alert, details { display: none !important; }
  .report-text { border: 0; height: auto !important; overflow: visible; }
}

.import-text { max-height: 14rem; overflow: auto; background: var(--bs-tertiary-bg); padding: .5rem; border-radius: .25rem; }
```

#### Download Bootstrap

The pages use Bootstrap for styling and Bootstrap Icons for icons. Download them into the
project so the app works without internet access. Run this in the terminal:

```powershell
$v = "casework\static\vendor"
New-Item -ItemType Directory -Force "$v\bootstrap", "$v\bootstrap-icons\fonts" | Out-Null
$cdn = "https://cdn.jsdelivr.net/npm"
Invoke-WebRequest "$cdn/bootstrap@5.3.3/dist/css/bootstrap.min.css"            -OutFile "$v\bootstrap\bootstrap.min.css"
Invoke-WebRequest "$cdn/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"       -OutFile "$v\bootstrap\bootstrap.bundle.min.js"
Invoke-WebRequest "$cdn/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css"   -OutFile "$v\bootstrap-icons\bootstrap-icons.min.css"
Invoke-WebRequest "$cdn/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2" -OutFile "$v\bootstrap-icons\fonts\bootstrap-icons.woff2"
Invoke-WebRequest "$cdn/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff"  -OutFile "$v\bootstrap-icons\fonts\bootstrap-icons.woff"
```

You should end up with five files under `casework\static\vendor`.

## 10. Run it for the first time

First add the VS Code run/debug configurations:


#### `.vscode/launch.json`

Four ready-made configurations for the **Run and Debug** panel: the development server,
the HTTPS server, loading sample data, and creating a self-signed certificate.

```jsonc
{
  // Run and Debug configurations (Ctrl+Shift+D, pick one, press F5)
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Casework: dev server (http://127.0.0.1:5000)",
      "type": "debugpy",
      "request": "launch",
      "module": "flask",
      "env": { "FLASK_APP": "run.py", "FLASK_DEBUG": "1" },
      "args": ["run", "--no-debugger", "--no-reload", "--port", "5000"],
      "jinja": true,
      "justMyCode": true
    },
    {
      "name": "Casework: HTTPS server (https://localhost:8443)",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/serve.py",
      "env": {
        "CASEWORK_SSL_CERT": "${workspaceFolder}/certs/cert.pem",
        "CASEWORK_SSL_KEY": "${workspaceFolder}/certs/key.pem",
        "CASEWORK_PORT": "8443"
      },
      "jinja": true
    },
    {
      "name": "Casework: load sample data",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/seed.py",
      "console": "integratedTerminal"
    },
    {
      "name": "Casework: create self-signed certificate",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/tls_cert.py",
      "args": ["self-signed"],
      "console": "integratedTerminal"
    }
  ]
}
```

#### `.vscode/settings.json`

Turns on pytest in the Testing panel and Jinja syntax colouring for templates.

```jsonc
{
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": ["tests"],
  "files.associations": { "**/templates/*.html": "jinja-html" },
  "emmet.includeLanguages": { "jinja-html": "html" }
}
```

#### `.vscode/extensions.json`

Suggests the recommended extensions to anyone who opens the project.

```jsonc
{
  "recommendations": [
    "ms-python.python",
    "ms-python.debugpy",
    "samuelcolvin.jinjahtml"
  ]
}
```

Now run it:

1. Open **Run and Debug** (**Ctrl+Shift+D**).
2. In the dropdown at the top, pick **Casework: dev server (http://127.0.0.1:5000)**.
3. Press **F5**.
4. Open <http://127.0.0.1:5000> in your browser (or **Ctrl+click** the link in the terminal).

You should see the dashboard with "No cases found". Click **New case**, fill in case number,
title and product, and save. Then try each tab: add an initial response, click
*Add standard scoping questions*, log a troubleshooting session, and so on.

The database file is created automatically at `instance\casework.db`.

**Debugging:** click in the margin to the left of a line number in any `.py` file (for example
inside `case_detail()` in `routes.py`) to set a red breakpoint, then reload the page. VS Code
pauses there and you can inspect variables. Press **F5** to continue, or **Shift+F5** to stop
the server.

**Changes to code:** this configuration doesn't auto-reload. Press **Ctrl+Shift+F5** to
restart after editing. If you'd rather auto-reload, run `python run.py` in the terminal
instead.

## 11. Add sample data


#### `seed.py`

Adds three example cases that are 2, 6 and 17 days old, so you can immediately see a normal
case, a case due for a swarm, and a case due for a structured investigation.

```python
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
```

Run it with **Run and Debug > Casework: load sample data > F5**, or in the terminal:

```powershell
python seed.py
```

Refresh the dashboard. **SAMPLE-1002** has a yellow *Swarm* badge and **SAMPLE-1003** a red *SI*
badge. Open SAMPLE-1002, go to the **Swarm / Investigation** tab, and click
**Generate swarm report**.

## 12. Add tests

Tests check the app still works after you change something.


#### `pytest.ini`

Tells pytest where the tests are and lets them import the `casework` package.

```ini
[pytest]
pythonpath = .
testpaths = tests
```

#### `tests/test_app.py`

Tests for the app: creating and validating cases, adding/editing/deleting entries on every
tab, the 5/15-day thresholds, the dashboard flags, the contents of both reports, and the
optional login. Each test uses a fresh in-memory database, so your real data is never touched.

```python
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
```

#### `tests/test_tls_cert.py`

Tests for the certificate helper you'll add in the next step.

```python
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12

import tls_cert


def test_self_signed_loads_into_ssl_context(tmp_path):
    cert = tls_cert.make_self_signed(str(tmp_path), ["casework.example.local", "localhost"], ["10.0.0.5"])
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "casework.example.local" in san.get_values_for_type(x509.DNSName)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
    assert (tmp_path / "casework.crt").exists()


def test_convert_pfx_keeps_intermediates_drops_root(tmp_path):
    # build root -> intermediate -> leaf, using the self-signed helper for keys/certs
    root = tls_cert.make_self_signed(str(tmp_path / "root"), ["root"], [])
    root_key = serialization.load_pem_private_key((tmp_path / "root" / "key.pem").read_bytes(), None)
    leaf = tls_cert.make_self_signed(str(tmp_path / "leaf"), ["leaf"], [])
    leaf_key = serialization.load_pem_private_key((tmp_path / "leaf" / "key.pem").read_bytes(), None)
    # re-sign leaf as issued by an "intermediate" (root key reused, different subject)
    inter_name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "intermediate")])
    inter = (x509.CertificateBuilder().subject_name(inter_name).issuer_name(root.subject)
             .public_key(root_key.public_key()).serial_number(1)
             .not_valid_before(root.not_valid_before_utc).not_valid_after(root.not_valid_after_utc)
             .sign(root_key, hashes.SHA256()))
    pfx = pkcs12.serialize_key_and_certificates(
        b"casework", leaf_key, leaf, [inter, root],
        serialization.BestAvailableEncryption(b"pw"))
    (tmp_path / "c.pfx").write_bytes(pfx)

    tls_cert.convert_pfx(str(tmp_path / "c.pfx"), str(tmp_path / "out"), "pw")
    pem = (tmp_path / "out" / "cert.pem").read_bytes()
    certs = x509.load_pem_x509_certificates(pem)
    assert [c.subject for c in certs] == [leaf.subject, inter.subject]
    ssl.create_default_context(ssl.Purpose.CLIENT_AUTH).load_cert_chain(
        tmp_path / "out" / "cert.pem", tmp_path / "out" / "key.pem")
```

Run the tests:

- **In VS Code:** open the **Testing** panel (the flask icon in the left bar). Click
  **Run Tests** (double play button). Each test gets a green tick or a red cross; click a red
  one to see why it failed.
- **In the terminal:** `pytest`

> `test_tls_cert.py` imports `tls_cert.py`, so it fails until you finish step 13. That's
> expected.

## 13. Add the production HTTPS server, certificates and backups

These files are what you'll use on Windows Server. Build and try them on your PC first.


#### `serve.py`

The production server (Cheroot). When `CASEWORK_SSL_CERT` and `CASEWORK_SSL_KEY` are set it
serves **HTTPS** on port 8443; otherwise plain HTTP on 8080. It warns you if the secret key or
login isn't configured.

```python
"""Production server (Cheroot) with optional HTTPS - use this instead of run.py on a server.

    python serve.py

Settings come from environment variables:
    CASEWORK_HOST              interface to listen on (default 0.0.0.0 = all network interfaces)
    CASEWORK_PORT              port (default 8443 with HTTPS, 8080 without)
    CASEWORK_THREADS           worker threads (default 10)
    CASEWORK_SSL_CERT          path to cert.pem  } set both to serve HTTPS
    CASEWORK_SSL_KEY           path to key.pem   } (create them with tls_cert.py)
    CASEWORK_SSL_KEY_PASSWORD  only if key.pem is password-protected
"""
import logging
import os
import sys

from cheroot import wsgi
from cheroot.ssl.builtin import BuiltinSSLAdapter

from casework import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("casework")

app = create_app()


def build_server():
    cert = os.environ.get("CASEWORK_SSL_CERT")
    key = os.environ.get("CASEWORK_SSL_KEY")
    use_tls = bool(cert or key)
    if use_tls:
        missing = [p for p in (cert, key) if not p or not os.path.isfile(p)]
        if missing or not (cert and key):
            sys.exit("HTTPS needs both CASEWORK_SSL_CERT and CASEWORK_SSL_KEY pointing at existing files "
                     f"(got cert={cert!r}, key={key!r}). Create them with: python tls_cert.py --help")

    host = os.environ.get("CASEWORK_HOST", "0.0.0.0")
    port = int(os.environ.get("CASEWORK_PORT", 8443 if use_tls else 8080))
    server = wsgi.Server(
        (host, port), app,
        numthreads=int(os.environ.get("CASEWORK_THREADS", 10)),
        server_name="casework",
    )
    if use_tls:
        server.ssl_adapter = BuiltinSSLAdapter(
            cert, key, private_key_password=os.environ.get("CASEWORK_SSL_KEY_PASSWORD") or None,
        )
        app.config["SESSION_COOKIE_SECURE"] = True

    if app.config["SECRET_KEY"] == "dev-change-me":
        log.warning("CASEWORK_SECRET_KEY is not set - set it to a long random value.")
    if not (app.config.get("CASEWORK_USERNAME") and app.config.get("CASEWORK_PASSWORD")):
        log.warning("No login configured - anyone who can reach this server can see your cases. "
                    "Set CASEWORK_USERNAME and CASEWORK_PASSWORD.")
    elif not use_tls:
        log.warning("Login is enabled without HTTPS - passwords cross the network unencrypted. "
                    "Set CASEWORK_SSL_CERT and CASEWORK_SSL_KEY.")
    scheme = "https" if use_tls else "http"
    log.info("Casework listening on %s://%s:%s", scheme, host, port)
    return server


if __name__ == "__main__":
    server = build_server()
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
```

#### `tls_cert.py`

Creates the certificate files HTTPS needs: either a **self-signed** certificate, or by
converting a **.pfx** from your company's certificate authority.

```python
"""Create or import the HTTPS certificate used by serve.py.

Two ways to get a certificate:

1) Self-signed (quick; each user's PC must trust it once, or browsers will warn):

       python tls_cert.py self-signed --name casework.mycompany.local --ip 10.0.0.25

2) Convert a .pfx/.p12 issued by your company's certificate authority (no browser warnings):

       python tls_cert.py from-pfx C:\\path\\to\\casework.pfx

Both write into ./certs (change with --out):
    cert.pem      certificate (+ any intermediate certificates) -> CASEWORK_SSL_CERT
    key.pem       private key, unencrypted -> CASEWORK_SSL_KEY.  Protect this file.
    casework.crt  (self-signed only) copy of the certificate to install on users' PCs
"""
import argparse
import datetime as dt
import getpass
import ipaddress
import os
import socket
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _write_key(path, key):
    _write(path, key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    try:
        os.chmod(path, 0o600)  # no-op on Windows; see docs for icacls
    except OSError:
        pass


def make_self_signed(out_dir, names, ips, days=730):
    """Generate a key and a self-signed server certificate covering `names` and `ips`."""
    os.makedirs(out_dir, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, names[0]),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Casework"),
    ])
    san = [x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_encipherment=True, content_commitment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    _write(os.path.join(out_dir, "cert.pem"), pem)
    _write(os.path.join(out_dir, "casework.crt"), pem)
    _write_key(os.path.join(out_dir, "key.pem"), key)
    return cert


def convert_pfx(pfx_path, out_dir, password=None):
    """Split a .pfx/.p12 into cert.pem (leaf + intermediates) and key.pem."""
    with open(pfx_path, "rb") as f:
        data = f.read()
    key, cert, extra = pkcs12.load_key_and_certificates(
        data, password.encode() if password else None
    )
    if key is None or cert is None:
        raise ValueError("The .pfx file must contain both a certificate and its private key.")
    os.makedirs(out_dir, exist_ok=True)
    chain = [cert] + [c for c in (extra or []) if c.subject != c.issuer]  # leave out root CAs
    _write(os.path.join(out_dir, "cert.pem"),
           b"".join(c.public_bytes(serialization.Encoding.PEM) for c in chain))
    _write_key(os.path.join(out_dir, "key.pem"), key)
    return cert


def _describe(cert, out_dir):
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = [str(v) for v in san.get_values_for_type(x509.DNSName)] + \
                [str(v) for v in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        names = []
    out = os.path.abspath(out_dir)
    print(f"Certificate for: {cert.subject.rfc4514_string()}")
    if names:
        print(f"Valid names:     {', '.join(names)}")
    print(f"Expires:         {cert.not_valid_after_utc:%Y-%m-%d}")
    print()
    print("Set these for the Casework service:")
    print(f"  CASEWORK_SSL_CERT={os.path.join(out, 'cert.pem')}")
    print(f"  CASEWORK_SSL_KEY={os.path.join(out, 'key.pem')}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("self-signed", help="generate a self-signed certificate")
    s.add_argument("--name", action="append", default=[],
                   help="DNS name users will type in the browser (repeatable). "
                        "The server's hostname and 'localhost' are always added.")
    s.add_argument("--ip", action="append", default=[], help="IP address users may browse to (repeatable)")
    s.add_argument("--days", type=int, default=730, help="validity in days (default 730)")
    s.add_argument("--out", default="certs")

    f = sub.add_parser("from-pfx", help="convert a .pfx/.p12 from your certificate authority")
    f.add_argument("pfx")
    f.add_argument("--password", help="PFX password (prompted if omitted)")
    f.add_argument("--out", default="certs")

    args = p.parse_args(argv)
    if args.cmd == "self-signed":
        host = socket.gethostname()
        names = list(dict.fromkeys(args.name + [host, socket.getfqdn(), "localhost"]))
        names = [n for n in names if n]
        ips = list(dict.fromkeys(args.ip + ["127.0.0.1"]))
        cert = make_self_signed(args.out, names, ips, args.days)
        _describe(cert, args.out)
        print()
        print(f"Install {os.path.join(os.path.abspath(args.out), 'casework.crt')} on users' PCs under "
              "'Trusted Root Certification Authorities' to avoid browser warnings.")
    else:
        password = args.password
        if password is None:
            password = getpass.getpass("PFX password (Enter if none): ")
        try:
            cert = convert_pfx(args.pfx, args.out, password or None)
        except ValueError as e:
            sys.exit(f"Could not read {args.pfx}: {e}")
        _describe(cert, args.out)


if __name__ == "__main__":
    main()
```

#### `backup.py`

Makes a safe copy of the database (even while the app is running) and removes old copies.

```python
"""Make a consistent copy of the SQLite database (safe while the app is running).

    python backup.py [backup_folder] [days_to_keep]

Defaults: backup folder = ./backups, keep 30 days. Schedule it daily with Task Scheduler.
"""
import os
import sqlite3
import sys
import time
from datetime import datetime

from casework import create_app


def main():
    target_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "backups")
    keep_days = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    app = create_app()
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///"):
        sys.exit(f"backup.py only handles SQLite databases, not {uri.split(':')[0]}")
    source = uri[len("sqlite:///"):]

    os.makedirs(target_dir, exist_ok=True)
    dest = os.path.join(target_dir, f"casework-{datetime.now():%Y%m%d-%H%M%S}.db")
    src_conn, dst_conn = sqlite3.connect(source), sqlite3.connect(dest)
    with dst_conn:
        src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()
    print(f"Backed up {source} -> {dest}")

    cutoff = time.time() - keep_days * 86400
    for name in os.listdir(target_dir):
        path = os.path.join(target_dir, name)
        if name.startswith("casework-") and name.endswith(".db") and os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"Removed old backup {name}")


if __name__ == "__main__":
    main()
```

Try HTTPS locally:

1. Create a self-signed certificate: **Run and Debug > Casework: create self-signed
   certificate > F5**, or `python tls_cert.py self-signed`. This writes `certs\cert.pem` and
   `certs\key.pem`.
2. Stop the dev server if it's running (**Shift+F5**).
3. Pick **Casework: HTTPS server (https://localhost:8443)** and press **F5**.
4. Open <https://localhost:8443>. Your browser warns that the certificate isn't trusted,
   which is expected for a self-signed one. Click *Advanced > Continue*. (The Windows Server
   guide explains how to make PCs trust it.)
5. Try the login: stop the server, open `.vscode\launch.json`, add
   `"CASEWORK_USERNAME": "me", "CASEWORK_PASSWORD": "test"` inside the HTTPS configuration's
   `"env"` block, and press **F5** again. The browser now asks for a username and password.
6. Run all tests again. They should all pass now.

Try a backup:

```powershell
python backup.py
```

It creates `backups\casework-<date-time>.db`.

## 14. Add Salesforce capture (Chrome extension)

This part lets a Chrome extension read the Salesforce case you have open and send it to
Casework, which sorts the feed into the tabs and lets you review it before importing.

**Server side.** First, add two tables to the end of `casework/models.py`. The full file in
step 6 already contains them (`ImportBatch` and `ImportedItem`), along with the
`imported_items` line in `Case`. If you typed step 6 from an older copy, add them now.
`casework/__init__.py` (step 6) already registers the `imports` blueprint and the API token
setting.


#### `casework/importer.py`

The brain of the import. It maps Salesforce fields (Subject, Status, Product & Topic,
Date/Time Opened...) onto Casework's case fields, and sorts each feed item: initial response,
scoping questions paired with the customer's reply, meetings, troubleshooting, notes, or
**ignored** (follow-ups, acknowledgements, automated posts, status changes). The phrase lists at
the top are what you edit to tune it.

```python
"""Turn a case captured by the Chrome extension into a reviewable import plan.

The extension sends what it could read from the Salesforce case page:

    {
      "caseNumber": "480570091",
      "userName": "Sathishkumar Ashok",          # the engineer (optional)
      "capturedAt": "2026-11-05T10:15:00Z",
      "fields": [{"label": "Status", "value": "Working"}, ...],
      "feed":   [{"author": "...", "timeText": "20h ago", "timeTitle": "...", "text": "..."}, ...]
    }

`build_plan()` maps the fields onto Casework's case fields and sorts every feed item into
one of the case tabs, or marks it ignored (follow-ups, acknowledgements, automation...).
Everything here is pure Python so it can be unit-tested and tuned without a browser.
"""

import hashlib
import re
from datetime import date, datetime, timedelta, timezone

from .models import STATUSES

# --------------------------------------------------------------------------- tunables
# Edit these lists to tune what gets ignored / how items are classified.

AUTOMATION_AUTHORS = [
    "automation", "system", "auto-response", "autoresponse", "no-reply", "noreply",
    "do not reply", "workflow", "process builder", "integration user",
]
AUTOMATION_TEXT = [
    r"system generated feed", r"this is an automated (message|response|email)",
    r"do not reply to this (email|message)", r"auto[- ]?generated",
]
STATUS_CHANGE_TEXT = [
    r"changed (the )?(status|sub-status|owner|priority|severity)", r"\bstatus changed\b",
    r"changed .+ from .+ to ", r"\bcreated this case\b", r"\bowner changed\b",
]
FOLLOW_UP_TEXT = [
    r"\bjust (a )?(quick |gentle )?(follow(ing)?[- ]?up|checking in)",
    r"\bfollow(ing)?[- ]?up on\b", r"\b(gentle|friendly|quick) (reminder|follow[- ]?up)\b",
    r"\bany updates?\b", r"\bchecking in\b", r"\bdid you (get|have) (a|the) chance\b",
    r"\b(have not|haven'?t|not) heard back\b", r"\bawaiting your (reply|response|update)\b",
    r"\bplease (provide|share) (an|the|your) update\b", r"\bwanted to check (if|whether)\b",
    r"\b(will|going to) (close|archive) (this|the) case\b", r"\bcase (will be|has been) (auto[- ]?)?closed\b",
    r"\bclosing (this|the) case\b", r"\bis it ok(ay)? (if we|to) close\b",
]
ACKNOWLEDGEMENT_TEXT = [
    r"\bthank(s| you)( very much| so much)? for (the |your )?(update|reply|response|sharing|details|"
    r"information|info|logs|files|confirmation|time|patience)",
    r"\bI will (check|review|look into|analy[sz]e|go through|get back|update you)",
    r"\bwe will (check|review|look into|analy[sz]e|get back|update you)",
    r"\b(noted|received|got it|sounds good|works for me)\b",
    r"\b(I|we) (have )?received (the|your)\b",
]
MEETING_TEXT = [
    r"\b(remote|screen[- ]?share|zoom|webex|teams|gotomeeting|google meet) (session|call|meeting)\b",
    r"\bmeeting (summary|notes|minutes|recap)\b", r"\bcall (summary|notes|recap)\b",
    r"\bas discussed (on|during|in) (the|our) (call|meeting|session)\b",
    r"\b(on|during) (the|our) (call|meeting|session) (today|yesterday|we)\b",
    r"\battendees\s*:", r"\bsummary of (the|our|today'?s) (call|meeting|session)\b",
]
TECHNICAL_TEXT = [
    r"\blogs?\b", r"\berror", r"\bexception", r"\bstack ?trace", r"\brepro(duc\w*)?\b",
    r"\btest(ed|ing)?\b", r"\btried\b", r"\bworkaround", r"\broot cause", r"\bbug\b",
    r"\bdebug", r"\bconfig(uration)?\b", r"\bdriver", r"\bsteps?\b", r"\bfiddler\b", r"\bhar\b",
    r"\bsaml\b", r"\bsso\b", r"\bcertificate", r"\bproxy\b", r"\bfirewall\b", r"\bregistry\b",
    r"\bversion\b", r"\bupgrade", r"\bpatch", r"\bconnection\b", r"\btimeout\b", r"\bcrash",
    r"\bqueries?\b", r"\bperformance\b", r"\bkb\d+|\bknowledge article\b", r"\bescalat",
]
SIGN_OFF = re.compile(
    r"^(best|kind|warm|warmest)?\s*regards\b.*$|^thanks?( (and|&) regards)?[,!.]?$|^thank you[,!.]?$|"
    r"^many thanks[,!.]?$|^cheers[,!.]?$|^sincerely[,!.]?$|^br[,.]?$|^--\s*$|^__+$",
    re.I,
)
QUOTE_START = re.compile(
    r"^on .{5,200} wrote:$|^-{2,}\s*original message|^-{2,}\s*forwarded message|"
    r"^from:\s.+|^sent:\s.+|^\s*>|^ref:[_!]|^thread::",
    re.I,
)
GREETING = re.compile(r"^(hi|hello|hey|dear|good (morning|afternoon|evening))\b[^.!?]{0,60}[,!.]?$", re.I)
UI_NOISE = re.compile(
    r"^(comment|like|liked|share|reply|reply all|forward|more|less|show more|show less|see more|"
    r"collapse post|expand post|edit|delete|bookmark|view more|view all|copy link|"
    r"actions for this (post|email|item).*|\d+ (comments?|likes?|views?)|write a comment\.*|"
    r"to: (all|internal|all with access)|internal|public|email|post|you|\.\.\.|·)$",
    re.I,
)
TIME_TEXT = re.compile(
    r"^(\d+\s*(s|sec|m|min|mins|h|hr|hrs|d|day|days|w|wk|wks)\s*ago|just now|yesterday.*|today.*|"
    r"[A-Z][a-z]+ \d{1,2},? \d{4}.*|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}.*)$",
    re.I,
)

FIELD_ALIASES = {
    "case_number": ["case number", "case no", "case #", "case id"],
    "title": ["subject", "case subject", "title"],
    "problem_description": ["description", "case description", "problem description", "issue description"],
    "status": ["status", "case status"],
    "sub_status": ["sub-status", "sub status", "substatus"],
    "severity": ["severity", "priority", "case severity", "case priority"],
    "product": ["product & topic", "product and topic", "product", "product name", "product/topic"],
    "product_feature": ["product feature", "feature", "topic", "component"],
    "version": ["version", "product version", "software version", "tableau version", "release"],
    "operating_system": ["operating system", "os", "platform", "os version", "operating system version"],
    "customer": ["account name", "account", "company", "customer", "organization"],
    "opened_on": ["date/time opened", "date time opened", "opened date", "date opened",
                  "created date", "case created date", "opened"],
}
CASE_FIELD_LABELS = {
    "case_number": "Case number", "title": "Title", "customer": "Customer", "product": "Product",
    "version": "Version", "operating_system": "Operating system", "severity": "Severity",
    "status": "Status", "opened_on": "Opened on", "problem_description": "Problem description",
}

CATEGORIES = ["initial_response", "scoping", "troubleshooting", "meeting", "note"]


def _any(patterns, text):
    return any(re.search(p, text, re.I) for p in patterns)


# --------------------------------------------------------------------------- fields

def _norm_label(label):
    label = re.sub(r"[*:]+", " ", label or "")
    label = re.sub(r"\b(help|info|edit)\b.*$", "", label, flags=re.I)
    return re.sub(r"\s+", " ", label).strip().lower()


def _clean_value(value):
    lines = [ln.strip() for ln in (value or "").splitlines()]
    lines = [ln for ln in lines if ln and not re.match(r"^(edit|change|open|help|view|preview)\b.{0,60}$", ln, re.I)]
    return "\n".join(lines).strip()


def map_fields(fields):
    """Map Salesforce label/value pairs onto Casework field names. First match wins."""
    by_label = {}
    for f in fields or []:
        label, value = _norm_label(f.get("label")), _clean_value(f.get("value"))
        if label and value and label not in by_label:
            by_label[label] = value
    mapped = {}
    for name, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in by_label:
                mapped[name] = by_label[alias]
                break
    return mapped, by_label


def map_status(value):
    v = (value or "").strip().lower()
    for s in STATUSES:
        if v == s.lower():
            return s
    if not v:
        return None
    if v in ("new", "open", "unassigned"):
        return "New"
    if "customer" in v or "pending" in v or "waiting" in v or "on hold" in v:
        return "Waiting on Customer"
    if "closed" in v:
        return "Closed"
    if "resolved" in v or "solution" in v or "solved" in v:
        return "Resolved"
    if "swarm" in v:
        return "Swarm"
    if "investigation" in v:
        return "Structured Investigation"
    return "In Progress"


def map_severity(value):
    v = (value or "").lower()
    if not v:
        return None
    if re.search(r"\b1\b|critical|urgent|sev ?1|p1", v):
        return "1 - Critical"
    if re.search(r"\b2\b|high|sev ?2|p2", v):
        return "2 - High"
    if re.search(r"\b3\b|medium|normal|sev ?3|p3", v):
        return "3 - Medium"
    if re.search(r"\b4\b|low|sev ?4|p4", v):
        return "4 - Low"
    return None


VERSION_RE = re.compile(
    r"\b(?:version|ver\.?|release)\s*[:#-]?\s*(\d{1,4}(?:\.\d+){1,3})\b|\b(20\d\d\.\d(?:\.\d+)?)\b", re.I
)
OS_RE = re.compile(
    r"\b(windows server \d{4}(?: r2)?|windows (?:10|11|7|8\.1)|mac ?os(?: x)?(?: \d+(?:\.\d+)*| [a-z]+)?|"
    r"os x [\d.]+|ubuntu(?: \d+\.\d+)?|rhel ?\d*(?:\.\d+)?|red hat(?: enterprise linux)?(?: \d+(?:\.\d+)?)?|"
    r"centos(?: \d+)?|amazon linux(?: \d+)?|linux|ios \d+|android \d+)\b",
    re.I,
)


def _guess_version(*texts):
    for t in texts:
        m = VERSION_RE.search(t or "")
        if m:
            return m.group(1) or m.group(2)
    return None


def _guess_os(*texts):
    for t in texts:
        m = OS_RE.search(t or "")
        if m:
            return m.group(1)
    return None


MONTH_FIRST = ["%m/%d/%Y, %I:%M %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y, %H:%M", "%m/%d/%Y %H:%M", "%m/%d/%Y"]
DAY_FIRST = ["%d/%m/%Y, %I:%M %p", "%d/%m/%Y %I:%M %p", "%d/%m/%Y, %H:%M", "%d/%m/%Y %H:%M", "%d/%m/%Y",
             "%d.%m.%Y, %H:%M", "%d.%m.%Y %H:%M", "%d.%m.%Y"]
DATE_FORMATS = [
    "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%B %d, %Y at %I:%M %p",
    "%B %d, %Y, %I:%M %p", "%B %d, %Y %I:%M %p", "%b %d, %Y, %I:%M %p", "%b %d, %Y at %I:%M %p",
    "%B %d, %Y", "%b %d, %Y", "%d %B %Y at %H:%M", "%d %b %Y, %H:%M", "%d %B %Y", "%d %b %Y",
    "%d-%b-%Y %H:%M", "%d-%b-%Y",
]


def parse_datetime(text, now, day_first=False):
    """Parse an absolute or relative Salesforce timestamp. Returns naive local datetime or None.

    `day_first` decides how 2/11/2026 is read (see detect_day_first)."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"\s*\((GMT|UTC)[^)]*\)$", "", t)
    t = re.sub(r"\s+(GMT|UTC|[A-Z]{2,4}T)([+-]\d{1,2}(:?\d{2})?)?$", "", t)
    if not t:
        return None
    m = re.match(r"^(\d+)\s*(s|sec|secs|m|min|mins|h|hr|hrs|d|day|days|w|wk|wks)\s*ago$", t, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[unit[0]]
        return now - timedelta(**{delta: n})
    if t.lower() == "just now":
        return now
    m = re.match(r"^(today|yesterday)(?: at)? (\d{1,2}:\d{2}(?: ?[AP]M)?)$", t, re.I)
    if m:
        base = now.date() - timedelta(days=1 if m.group(1).lower() == "yesterday" else 0)
        clock = m.group(2).upper().replace(" ", "")
        for fmt in ("%I:%M%p", "%H:%M"):
            try:
                return datetime.combine(base, datetime.strptime(clock, fmt).time())
            except ValueError:
                pass
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        pass
    numeric = (DAY_FIRST + MONTH_FIRST) if day_first else (MONTH_FIRST + DAY_FIRST)
    for fmt in numeric + DATE_FORMATS:
        try:
            parsed = datetime.strptime(t, fmt)
        except ValueError:
            continue
        # Something that already happened can't be in the future: try day and month swapped.
        if fmt in numeric and parsed > now + timedelta(days=1) and parsed.day <= 12:
            swapped = parsed.replace(month=parsed.day, day=parsed.month)
            if swapped <= now + timedelta(days=1):
                return swapped
        return parsed
    return None


NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")
RELATIVE = re.compile(r"^\d+\s*[a-z]+\s*ago$|^(today|yesterday)\b", re.I)


def detect_day_first(payload, now):
    """Work out whether this Salesforce shows dates as day/month or month/day."""
    texts = [f.get("value") or "" for f in payload.get("fields") or []]
    texts += [i.get("timeTitle") or "" for i in payload.get("feed") or []]
    for t in texts:
        for a, b, _ in NUMERIC_DATE.findall(t):
            if int(a) > 12 >= int(b):
                return True
            if int(b) > 12 >= int(a):
                return False
    # Compare each post's exact date with its "3d ago" label: only one reading will agree.
    votes = 0
    for i in payload.get("feed") or []:
        rel, title = i.get("timeText") or "", i.get("timeTitle") or ""
        if not (RELATIVE.match(rel.strip()) and NUMERIC_DATE.search(title)):
            continue
        approx = parse_datetime(rel, now)
        md, dm = parse_datetime(title, now, False), parse_datetime(title, now, True)
        if approx and md and dm and md != dm:
            votes += 1 if abs(dm - approx) < abs(md - approx) else -1
    return votes > 0


# --------------------------------------------------------------------------- feed items

def _lines(text):
    return [re.sub(r"[ \t ]+", " ", ln).strip() for ln in (text or "").replace("\r", "").split("\n")]


def strip_noise(text, author=None):
    """Remove feed chrome (author, 'To: All', timestamps, Like/Comment buttons) from an item's text."""
    out = []
    a = (author or "").strip().lower()
    for i, ln in enumerate(_lines(text)):
        if not ln:
            out.append("")
            continue
        if UI_NOISE.match(ln) or (a and ln.lower() == a and i < 4) or (i < 6 and TIME_TEXT.match(ln)):
            continue
        out.append(ln)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_email_header(text):
    """If the item is an email, return (headers dict, body). Otherwise ({}, text)."""
    lines = text.split("\n")
    headers, i = {}, 0
    while i < len(lines) and i < 12:
        m = re.match(r"^(from|to|cc|bcc|subject|sent|date)\s*:\s*(.*)$", lines[i], re.I)
        if m:
            headers[m.group(1).lower()] = m.group(2).strip()
        elif lines[i].strip() and headers:
            break
        i += 1
    if "from" in headers or "subject" in headers:
        return headers, "\n".join(lines[i:]).strip()
    return {}, text


def clean_body(text):
    """Drop greeting, quoted earlier messages and the signature, keeping the actual message."""
    kept = []
    for ln in text.split("\n"):
        s = ln.strip()
        if kept and QUOTE_START.match(s):
            break
        if s.startswith(">"):
            continue
        if SIGN_OFF.match(s) and any(k.strip() for k in kept):
            break
        kept.append(ln)
    while kept and (not kept[0].strip() or GREETING.match(kept[0].strip())):
        kept.pop(0)
    body = "\n".join(kept).strip()
    return re.sub(r"\n{3,}", "\n\n", body)


def extract_questions(text):
    qs = []
    asks = re.search(r"\b(please (provide|confirm|share|send|let (me|us) know|check)|could you|can you)\b", text, re.I)
    for ln in text.split("\n"):
        s = ln.strip()
        if len(s) < 8:
            continue
        if s.endswith("?") or (asks and re.match(r"^(\d+[.)]|[-*•])\s+\S", s)):
            qs.append(s)
    return qs


def _words(text):
    return len(re.findall(r"\w+", text))


def item_key(item):
    raw = "|".join([
        (item.get("author") or "").strip().lower(),
        (item.get("timeTitle") or item.get("timeText") or "").strip().lower(),
        re.sub(r"\s+", " ", (item.get("text") or "")).strip()[:400].lower(),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _title(body, fallback):
    first = next((ln.strip() for ln in body.split("\n") if ln.strip()), "")
    first = re.sub(r"\s+", " ", first)
    if not first:
        return fallback
    return first if len(first) <= 80 else first[:77].rsplit(" ", 1)[0] + "..."


def classify_item(raw, engineer, now, day_first=False):
    """Analyse one feed item. Returns a dict describing it and why it is kept or ignored."""
    author = (raw.get("author") or "").strip()
    full = raw.get("text") or ""
    visibility = None
    m = re.search(r"^\s*to:\s*(all with access|all|internal)\s*$", full, re.I | re.M)
    if m:
        visibility = "internal" if m.group(1).lower() == "internal" else "public"
    text = strip_noise(full, author)
    if not author:
        first = next((ln for ln in text.split("\n") if ln.strip()), "")
        if 2 <= len(first.split()) <= 5 and not first.endswith((".", "?", ":")):
            author, text = first.strip(), text.split("\n", 1)[1] if "\n" in text else ""
    headers, body = split_email_header(text)
    kind = "email" if headers else "post"
    if headers.get("from") and not author:
        author = re.sub(r"<.*?>", "", headers["from"]).strip()
    clean = clean_body(body)
    when = (parse_datetime(raw.get("timeTitle"), now, day_first) or parse_datetime(raw.get("timeText"), now, day_first))

    a = author.lower()
    if any(k in a for k in AUTOMATION_AUTHORS):
        direction = "system"
    elif engineer and (a == engineer.lower() or engineer.lower() in a
                       or (headers.get("from") and engineer.lower() in headers["from"].lower())):
        direction = "outbound"
    else:
        direction = "inbound"

    item = {
        "key": item_key(raw), "author": author or "Unknown", "when": when, "kind": kind,
        "visibility": visibility, "direction": direction, "subject": headers.get("subject"),
        "clean": clean, "words": _words(clean), "include": True, "reason": None,
        "category": "note", "title": None, "question": None, "response": None, "consumed_by": None,
    }

    def ignore(reason):
        item.update(include=False, reason=reason)
        return item

    if direction == "system" or _any(AUTOMATION_TEXT, full):
        return ignore("Automated / system message")
    if _any(STATUS_CHANGE_TEXT, clean) and item["words"] < 40:
        return ignore("Status or field change")
    if item["words"] < 6:
        return ignore("Too short to be useful")
    if item["words"] < 80 and _any(FOLLOW_UP_TEXT, clean):
        return ignore("Follow-up / reminder")
    if item["words"] < 60 and _any(ACKNOWLEDGEMENT_TEXT, clean) and not extract_questions(clean):
        return ignore("Acknowledgement with no new information")

    questions = extract_questions(clean)
    if _any(MEETING_TEXT, clean):
        item.update(category="meeting", title=_title(clean, "Meeting"))
    elif direction == "outbound" and questions:
        item.update(category="scoping", question="\n".join(questions))
    elif direction == "outbound" and visibility == "internal":
        item.update(category="troubleshooting" if _any(TECHNICAL_TEXT, clean) else "note",
                    title=_title(clean, "Internal note"))
    elif direction == "outbound" and _any(TECHNICAL_TEXT, clean):
        item.update(category="troubleshooting", title=_title(clean, "Troubleshooting update"))
    elif direction == "inbound":
        item.update(category="note", title=f"Customer update from {author or 'customer'}")
    else:
        item.update(category="note", title=_title(clean, "Update"))
    if questions:
        item["question"] = "\n".join(questions)
    return item


def build_plan(payload, already_imported=frozenset(), now=None):
    """Full import plan: mapped case fields + every feed item classified, oldest first."""
    now = now or datetime.now()
    # Relative times ("20h ago") are relative to when the page was captured, not to now.
    now = parse_datetime(payload.get("capturedAt") or "", now) or now

    day_first = detect_day_first(payload, now)
    mapped, raw_fields = map_fields(payload.get("fields"))
    engineer = (payload.get("userName") or "").strip() or None
    owner = raw_fields.get("case owner") or raw_fields.get("owner") or raw_fields.get("owner name")
    if not engineer and owner:
        engineer = owner.split("\n")[0].strip()

    case_number = (payload.get("caseNumber") or mapped.get("case_number") or "").strip()
    if not case_number:
        m = re.search(r"\b(\d{5,})\b", payload.get("title") or "")
        case_number = m.group(1) if m else ""

    product = mapped.get("product")
    if product and mapped.get("product_feature"):
        product = f"{product} / {mapped['product_feature']}"
    elif not product:
        product = mapped.get("product_feature")
    description = mapped.get("problem_description")
    opened = parse_datetime(mapped.get("opened_on"), now, day_first)

    case = {
        "case_number": case_number or None,
        "title": mapped.get("title"),
        "customer": (mapped.get("customer") or "").split("\n")[0] or None,
        "product": product,
        "version": mapped.get("version") or _guess_version(description, mapped.get("title")),
        "operating_system": mapped.get("operating_system") or _guess_os(description, mapped.get("title")),
        "severity": map_severity(mapped.get("severity")),
        "status": map_status(mapped.get("status")),
        "opened_on": opened.date() if opened else None,
        "problem_description": description,
    }

    # Salesforce shows newest first; reverse so ties keep chronological order, then sort by time.
    raw_items = list(reversed(payload.get("feed") or []))
    items = [classify_item(r, engineer, now, day_first) for r in raw_items]
    items.sort(key=lambda i: i["when"] or datetime.max)

    seen = set()
    for it in items:
        if it["key"] in seen:
            it.update(include=False, reason="Duplicate of another item")
        seen.add(it["key"])
        if it["key"] in already_imported:
            it.update(include=False, reason="Already imported", already=True)

    # First substantive outbound message becomes the initial response.
    first_out = next((i for i in items if i["include"] and i["direction"] == "outbound"
                      and i["visibility"] != "internal" and i["category"] != "meeting"), None)
    if first_out:
        first_out.update(category="initial_response", title=first_out["subject"] or "Initial response")

    # Pair each set of scoping questions with the customer's next reply.
    for idx, it in enumerate(items):
        if not (it["include"] and it["question"] and it["category"] in ("scoping", "initial_response")):
            continue
        for nxt in items[idx + 1:]:
            if nxt["direction"] == "outbound" and nxt["include"]:
                break
            if nxt["direction"] == "inbound" and nxt["include"] and not nxt["consumed_by"]:
                it["response"] = nxt["clean"]
                nxt.update(include=False, consumed_by=it["key"],
                           reason="Used as the answer to the scoping questions above")
                break

    return {
        "case": case,
        "engineer": engineer,
        "items": items,
        "raw_fields": raw_fields,
        "warnings": list(payload.get("warnings") or []),
        "counts": {
            "total": len(items),
            "included": sum(1 for i in items if i["include"]),
            "ignored": sum(1 for i in items if not i["include"]),
        },
    }
```

#### `casework/imports.py`

The `/api/import` endpoint the extension sends to (protected by `CASEWORK_API_TOKEN`), and
the review page where you confirm what gets imported.

```python
"""Import cases captured by the Chrome extension: API endpoint + review screen."""

import hmac
import json
import secrets
from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .entry_types import ENTRY_TYPES
from .importer import CASE_FIELD_LABELS, CATEGORIES, build_plan
from .models import SEVERITIES, STATUSES, Case, Entry, ImportBatch, ImportedItem, db

bp = Blueprint("imports", __name__)


# --------------------------------------------------------------------------- API

@bp.after_app_request
def _cors_for_extension(response):
    """Let the Chrome extension call /api/ (it is still protected by the API token)."""
    origin = request.headers.get("Origin", "")
    if request.path.startswith("/api/") and origin.startswith("chrome-extension://"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


def _api_allowed():
    token = current_app.config.get("CASEWORK_API_TOKEN")
    if token:
        header = request.headers.get("Authorization", "")
        given = header[7:].strip() if header.lower().startswith("bearer ") else ""
        return hmac.compare_digest(given.encode(), token.encode())
    # No token configured: only allowed when the app has no login either (local, single-user use).
    return not (current_app.config.get("CASEWORK_USERNAME") and current_app.config.get("CASEWORK_PASSWORD"))


def _api_denied():
    msg = ("Invalid or missing API token." if current_app.config.get("CASEWORK_API_TOKEN")
           else "This server has a login, so set CASEWORK_API_TOKEN on the server and the same token in the extension.")
    return jsonify(ok=False, error=msg), 401


@bp.route("/api/ping")
def api_ping():
    if not _api_allowed():
        return _api_denied()
    return jsonify(ok=True, app="casework")


@bp.route("/api/import", methods=["POST"])
def api_import():
    if not _api_allowed():
        return _api_denied()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not (data.get("feed") or data.get("fields")):
        return jsonify(ok=False, error="Nothing to import: no case fields or feed items were captured."), 400

    # Tidy up captures that were never reviewed (older than 30 days).
    ImportBatch.query.filter(ImportBatch.applied_at.is_(None),
                             ImportBatch.created_at < datetime.now() - timedelta(days=30)).delete()
    plan = build_plan(data)
    batch = ImportBatch(token=secrets.token_urlsafe(16), case_number=plan["case"]["case_number"],
                        payload=json.dumps(data))
    db.session.add(batch)
    db.session.commit()
    return jsonify(
        ok=True,
        caseNumber=plan["case"]["case_number"],
        counts=plan["counts"],
        reviewUrl=url_for("imports.review", token=batch.token, _external=True),
    )


# --------------------------------------------------------------------------- review

def _load(token):
    batch = ImportBatch.query.filter_by(token=token).first() or abort(404)
    payload = json.loads(batch.payload)
    number = build_plan(payload)["case"]["case_number"]
    existing = Case.query.filter_by(case_number=number).first() if number else None
    already = {i.key for i in existing.imported_items} if existing else set()
    plan = build_plan(payload, already_imported=already)
    return batch, payload, plan, existing


def _field_rows(plan, existing):
    rows = []
    for name, label in CASE_FIELD_LABELS.items():
        new = plan["case"].get(name)
        cur = getattr(existing, name) if existing else None
        if isinstance(new, date):
            new = new.isoformat()
        if isinstance(cur, date):
            cur = cur.isoformat()
        if name == "case_number" and existing:
            continue
        rows.append({
            "name": name, "label": label, "new": new or "", "current": cur or "",
            "checked": bool(new) and (not existing or not cur),
            "differs": bool(new) and bool(cur) and str(new).strip() != str(cur).strip(),
        })
    return rows


@bp.route("/import/<token>", methods=["GET"])
def review(token):
    batch, payload, plan, existing = _load(token)
    if batch.applied_at:
        flash("This capture was already imported.", "info")
        if batch.case_id and db.session.get(Case, batch.case_id):
            return redirect(url_for("main.case_detail", case_id=batch.case_id))
    return render_template(
        "import_review.html", batch=batch, payload=payload, plan=plan, existing=existing,
        rows=_field_rows(plan, existing), categories=CATEGORIES, statuses=STATUSES, severities=SEVERITIES,
    )


def _apply_fields(case, form, is_new):
    for name in CASE_FIELD_LABELS:
        if name == "case_number" and not is_new:
            continue
        if not form.get(f"apply_{name}"):
            continue
        value = (form.get(f"value_{name}") or "").strip()
        if not value:
            continue
        if name == "opened_on":
            try:
                case.opened_on = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                flash(f"Ignored invalid opened date '{value}' (use YYYY-MM-DD).", "warning")
        elif name == "status":
            if value in STATUSES:
                case.status = value
        elif name == "severity":
            if value in SEVERITIES:
                case.severity = value
        else:
            setattr(case, name, value)


def _entries_for(item, category):
    when = item["when"] or datetime.now()
    body = item["clean"]
    if category == "initial_response":
        out = [Entry(entry_type="initial_response", occurred_at=when, title=item["title"] or item["subject"],
                     body=body)]
        if item["question"]:
            out.append(Entry(entry_type="scoping", occurred_at=when, question=item["question"],
                             response=item["response"]))
        return out
    if category == "scoping":
        return [Entry(entry_type="scoping", occurred_at=when, question=item["question"] or body,
                      response=item["response"])]
    if item["response"]:
        body += f"\n\nCustomer reply:\n{item['response']}"
    title = item["title"] or item["subject"] or ENTRY_TYPES[category]["singular"].capitalize()
    return [Entry(entry_type=category, occurred_at=when, title=title[:255], body=body)]


@bp.route("/import/<token>", methods=["POST"])
def apply(token):
    batch, payload, plan, existing = _load(token)
    if batch.applied_at:
        flash("This capture was already imported.", "info")
        return redirect(url_for("main.dashboard"))
    form = request.form

    case = existing
    if case is None:
        case = Case(status="In Progress", opened_on=date.today())
        _apply_fields(case, form, is_new=True)
        if not case.case_number:
            case.case_number = (form.get("value_case_number") or plan["case"]["case_number"] or "").strip()
        if not case.case_number:
            flash("A case number is needed to create the case.", "danger")
            return redirect(url_for("imports.review", token=token))
        if Case.query.filter_by(case_number=case.case_number).first():
            flash(f"Case {case.case_number} already exists.", "danger")
            return redirect(url_for("imports.review", token=token))
        case.title = case.title or f"Case {case.case_number}"
        case.product = case.product or "Unknown"
        db.session.add(case)
    else:
        _apply_fields(case, form, is_new=False)

    known = {i.key for i in case.imported_items}
    added = 0
    for item in plan["items"]:
        if not form.get(f"include_{item['key']}"):
            continue
        category = form.get(f"cat_{item['key']}")
        if category not in CATEGORIES:
            category = item["category"]
        for entry in _entries_for(item, category):
            entry.case = case
            db.session.add(entry)
            added += 1
        keys = {item["key"]} | {i["key"] for i in plan["items"] if i["consumed_by"] == item["key"]}
        for k in keys - known:
            case.imported_items.append(ImportedItem(key=k))
            known.add(k)

    batch.applied_at = datetime.now()
    db.session.flush()
    batch.case_id = case.id
    db.session.commit()
    flash(f"Imported {added} entr{'y' if added == 1 else 'ies'} into case {case.case_number}.", "success")
    return redirect(url_for("main.case_detail", case_id=case.id) + "#tab-timeline")
```

#### `casework/templates/import_review.html`

The review screen: case fields to apply, items to import (with the tab each goes to), and the ignored items with reasons.

```jinja
{% extends "base.html" %}
{% block title %}Review import{% endblock %}

{% macro direction_badge(it) %}
  {% if it.direction == 'outbound' %}<span class="badge text-bg-primary">You</span>
  {% elif it.direction == 'inbound' %}<span class="badge text-bg-success">Customer</span>
  {% else %}<span class="badge text-bg-secondary">System</span>{% endif %}
  {% if it.visibility == 'internal' %}<span class="badge text-bg-warning">Internal</span>{% endif %}
  {% if it.kind == 'email' %}<span class="badge text-bg-light border">Email</span>{% endif %}
{% endmacro %}

{% macro item_card(it, checked) %}
  <div class="card mb-2 import-item {% if not checked %}opacity-75{% endif %}">
    <div class="card-body py-2">
      <div class="d-flex flex-wrap align-items-center gap-2 mb-1">
        <input class="form-check-input mt-0" type="checkbox" name="include_{{ it.key }}" value="1"
               id="inc-{{ it.key }}" {% if checked %}checked{% endif %}>
        <label class="fw-semibold" for="inc-{{ it.key }}">{{ it.author }}</label>
        {{ direction_badge(it) }}
        <span class="text-body-secondary small">{{ it.when|dt if it.when else 'time unknown' }}</span>
        {% if it.reason %}<span class="badge text-bg-light border text-wrap">{{ it.reason }}</span>{% endif %}
        <select class="form-select form-select-sm ms-auto w-auto" name="cat_{{ it.key }}" aria-label="Import as">
          {% for c in categories %}
            <option value="{{ c }}" {% if c == it.category %}selected{% endif %}>{{ ENTRY_TYPES[c].label }}</option>
          {% endfor %}
        </select>
      </div>
      {% if it.subject %}<div class="small"><strong>Subject:</strong> {{ it.subject }}</div>{% endif %}
      {% if it.question and it.category in ('scoping', 'initial_response') %}
        <div class="small mt-1"><strong>Scoping questions:</strong></div>
        <div class="prewrap small import-text">{{ it.question }}</div>
        <div class="small mt-1"><strong>Customer answer:</strong></div>
        <div class="prewrap small import-text">{{ it.response or 'No reply found yet.' }}</div>
        {% if it.category == 'initial_response' %}
          <details class="small mt-1"><summary>Full message</summary><div class="prewrap import-text">{{ it.clean }}</div></details>
        {% endif %}
      {% else %}
        <div class="prewrap small import-text">{{ it.clean or '(empty)' }}</div>
      {% endif %}
    </div>
  </div>
{% endmacro %}

{% block content %}
{% set included = plan['items']|selectattr('include')|list %}
{% set already = plan['items']|selectattr('already')|list %}
{% set ignored = plan['items']|rejectattr('include')|rejectattr('already')|list %}

<div class="d-flex flex-wrap align-items-center gap-2 mb-3">
  <h1 class="h4 mb-0">Review import · Case {{ plan.case.case_number or '(no number found)' }}</h1>
  {% if existing %}
    <span class="badge text-bg-info">Updating existing case</span>
  {% else %}
    <span class="badge text-bg-success">New case</span>
  {% endif %}
  {% if payload.url %}<a class="ms-auto small" href="{{ payload.url }}" target="_blank" rel="noopener">Open in Salesforce</a>{% endif %}
</div>

{% for w in plan.warnings %}<div class="alert alert-warning py-2">{{ w }}</div>{% endfor %}
{% if not plan['items'] %}
  <div class="alert alert-warning">No feed items were captured. Make sure the case feed is visible
    (e.g. the <em>All Updates</em> tab) before capturing.</div>
{% endif %}

<form method="post">
  <div class="card mb-4">
    <div class="card-header fw-semibold">Case details</div>
    <div class="card-body">
      <p class="small text-body-secondary mb-2">Ticked fields are written to the case. You can edit the values first.
        {% if existing %}Fields that already have a value in Casework are unticked by default.{% endif %}</p>
      <div class="table-responsive">
      <table class="table table-sm align-middle mb-0">
        <thead><tr><th style="width:2rem"></th><th>Field</th><th>From Salesforce</th>{% if existing %}<th>Currently in Casework</th>{% endif %}</tr></thead>
        <tbody>
        {% for r in rows %}
          <tr>
            <td><input class="form-check-input" type="checkbox" name="apply_{{ r.name }}" value="1" {% if r.checked %}checked{% endif %} aria-label="Apply {{ r.label }}"></td>
            <td class="text-nowrap">{{ r.label }}{% if r.differs %} <span class="badge text-bg-warning">differs</span>{% endif %}</td>
            <td>
              {% if r.name == 'problem_description' %}
                <textarea class="form-control form-control-sm" rows="3" name="value_{{ r.name }}">{{ r.new }}</textarea>
              {% elif r.name == 'status' %}
                <select class="form-select form-select-sm" name="value_status">
                  {% for s in statuses %}<option {% if s == r.new %}selected{% endif %}>{{ s }}</option>{% endfor %}
                </select>
              {% elif r.name == 'severity' %}
                <select class="form-select form-select-sm" name="value_severity">
                  <option value="">-</option>
                  {% for s in severities %}<option {% if s == r.new %}selected{% endif %}>{{ s }}</option>{% endfor %}
                </select>
              {% elif r.name == 'opened_on' %}
                <input class="form-control form-control-sm" type="date" name="value_opened_on" value="{{ r.new }}">
              {% else %}
                <input class="form-control form-control-sm" name="value_{{ r.name }}" value="{{ r.new }}">
              {% endif %}
            </td>
            {% if existing %}<td class="small prewrap text-body-secondary">{{ r.current|truncate(200) }}</td>{% endif %}
          </tr>
        {% endfor %}
        </tbody>
      </table>
      </div>
      {% if plan.raw_fields %}
        <details class="small mt-2"><summary>All {{ plan.raw_fields|length }} fields read from the page</summary>
          <table class="table table-sm mt-2">
            {% for k, v in plan.raw_fields.items() %}<tr><td class="text-nowrap">{{ k }}</td><td class="prewrap">{{ v|truncate(300) }}</td></tr>{% endfor %}
          </table>
        </details>
      {% endif %}
    </div>
  </div>

  <h2 class="h5">To import <span class="badge text-bg-primary">{{ included|length }}</span></h2>
  <p class="small text-body-secondary">Untick anything you don't want, or change which tab it goes to.
    {% if plan.engineer %}Messages from <strong>{{ plan.engineer }}</strong> are treated as yours.{% endif %}</p>
  {% for it in included %}{{ item_card(it, True) }}{% else %}<p class="text-body-secondary">Nothing selected for import.</p>{% endfor %}

  {% if ignored %}
  <details class="mt-4" {% if not included %}open{% endif %}>
    <summary class="h5 d-inline">Ignored <span class="badge text-bg-secondary">{{ ignored|length }}</span></summary>
    <p class="small text-body-secondary mt-2">Follow-ups, acknowledgements, automated posts and answers already attached to
      scoping questions. Tick any you want after all.</p>
    {% for it in ignored %}{{ item_card(it, False) }}{% endfor %}
  </details>
  {% endif %}

  {% if already %}
  <details class="mt-3">
    <summary class="h6 d-inline">Already imported earlier <span class="badge text-bg-light border">{{ already|length }}</span></summary>
    <div class="mt-2">{% for it in already %}{{ item_card(it, False) }}{% endfor %}</div>
  </details>
  {% endif %}

  <div class="position-sticky bottom-0 bg-body border-top py-3 mt-4 d-flex gap-2">
    <button class="btn btn-primary"><i class="bi bi-box-arrow-in-down"></i> Import into Casework</button>
    <a class="btn btn-outline-secondary" href="{{ url_for('main.dashboard') }}">Cancel</a>
  </div>
</form>
{% endblock %}
```

Add this line to the end of `casework/static/style.css` (the full file in step 9 already has it):

```css
.import-text { max-height: 14rem; overflow: auto; background: var(--bs-tertiary-bg); padding: .5rem; border-radius: .25rem; }
```

**The extension.** Create a folder `chrome-extension` in the project root, and `chrome-extension\icons`
inside it, then add these files:


#### `chrome-extension/manifest.json`

Tells Chrome what the extension is and what it may do: run on the tab you click it in (`activeTab`), inject a script (`scripting`), and save settings (`storage`).

```jsonc
{
  "manifest_version": 3,
  "name": "Casework Capture",
  "version": "1.0.0",
  "description": "Send the Salesforce case you're viewing (details and case feed) to your Casework app for review and import.",
  "permissions": ["activeTab", "scripting", "storage"],
  "action": {
    "default_popup": "popup.html",
    "default_title": "Send this case to Casework",
    "default_icon": { "16": "icons/icon16.png", "48": "icons/icon48.png", "128": "icons/icon128.png" }
  },
  "options_page": "options.html",
  "background": { "service_worker": "background.js" },
  "icons": { "16": "icons/icon16.png", "48": "icons/icon48.png", "128": "icons/icon128.png" }
}
```

#### `chrome-extension/extractor.js`

Runs inside the Salesforce page. Salesforce Lightning hides most of the page inside *shadow DOM*,
so this walks into it to find the case fields and feed posts. It only reads visible elements,
so other console tabs open in the background are ignored. It can also click **Show More** and
**View More** so the whole feed is captured.

```
/*
 * Reads the case that is open in the Salesforce Lightning console.
 * Injected into the page by popup.js; defines window.__caseworkExtract(options).
 *
 * Lightning renders most of the page inside (synthetic or native) shadow DOM, so normal
 * document.querySelectorAll() can't see it. Everything here walks shadow roots, and only
 * looks at elements that are visible, so other console tabs open in the background
 * (which Salesforce keeps in the page but hides) are ignored.
 */
(function () {
  'use strict';

  var FIELD_ITEM = 'records-record-layout-item, .slds-form-element, force-record-layout-item, .forcePageBlockItem';
  var FIELD_LABEL = '.test-id__field-label, .slds-form-element__label, .test-id__field-label-container';
  var FIELD_VALUE = '.test-id__field-value, .slds-form-element__static, .slds-form-element__control, .itemBody';
  var FEED_ITEM = '.cuf-feedElement, .cuf-feedItem, article.forceChatterFeedItem, [class*="feedElement"], [class*="FeedItem"], [data-feed-item-id], [data-feed-element-id]';
  var FEED_AUTHOR = '.cuf-entityLink, a.forceChatterEntityLink, [class*="actorName"], [class*="entityLink"], .slds-media__body a[data-recordid], .slds-media__body a';
  var FEED_TIME = '.cuf-timestamp, [class*="timeStamp"], [class*="timestamp"], lightning-formatted-date-time, lightning-relative-date-time, time';
  var SKIP_CLASS = /(^|\s)(assistiveText|slds-assistive-text|slds-hide|hidden)(\s|$)/;

  function children(node) {
    // Shadow content first (if any), then light children (which are slotted into it).
    var out = [];
    if (node.shadowRoot) out.push.apply(out, node.shadowRoot.children);
    if (node.children) out.push.apply(out, node.children);
    return out;
  }

  function deepQueryAll(root, selector) {
    var found = [], stack = [root];
    while (stack.length) {
      var n = stack.pop();
      if (n.nodeType === 1 && n.matches(selector)) found.push(n);
      var kids = children(n);
      for (var i = kids.length - 1; i >= 0; i--) stack.push(kids[i]);
    }
    return found;
  }

  function deepQuery(root, selector) {
    var all = deepQueryAll(root, selector);
    return all.length ? all[0] : null;
  }

  function isVisible(el) {
    if (!el.getClientRects || !el.getClientRects().length) return false;
    var cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none';
  }

  function composedParent(n) {
    return n.parentNode && n.parentNode.nodeType === 11 ? n.parentNode.host : n.parentNode;
  }

  function isInside(el, set) {
    for (var p = composedParent(el); p; p = composedParent(p)) if (set.has(p)) return true;
    return false;
  }

  var BLOCK = /^(block|flex|grid|list-item|table|table-row|flow-root)$/;

  // Visible text of an element, walking shadow roots and slots, with line breaks between blocks.
  function deepText(root) {
    var parts = [];
    (function walk(node) {
      if (node.nodeType === 3) { parts.push(node.nodeValue); return; }
      if (node.nodeType !== 1 && node.nodeType !== 11) return;
      if (node.nodeType === 1) {
        var tag = node.tagName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEMPLATE' || tag === 'SVG' || tag === 'svg') return;
        if (typeof node.className === 'string' && SKIP_CLASS.test(node.className)) return;
        if (tag === 'BR') { parts.push('\n'); return; }
        var cs = getComputedStyle(node);
        if (cs.display === 'none' || cs.visibility === 'hidden') return;
        var block = BLOCK.test(cs.display) || /^(P|DIV|LI|TR|BUTTON|H[1-6])$/.test(tag);
        if (block) parts.push('\n');
        if (tag === 'SLOT') {
          node.assignedNodes({ flatten: true }).forEach(walk);
        } else if (node.shadowRoot) {
          Array.prototype.forEach.call(node.shadowRoot.childNodes, walk);
        } else {
          Array.prototype.forEach.call(node.childNodes, walk);
        }
        if (block) parts.push('\n');
        return;
      }
      Array.prototype.forEach.call(node.childNodes, walk);  // shadow root
    })(root);
    return parts.join('')
      .replace(/[ \t ]+/g, ' ')
      .split('\n').map(function (l) { return l.trim(); }).join('\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function visibleFeedItems() {
    var items = deepQueryAll(document, FEED_ITEM).filter(isVisible);
    var set = new Set(items);
    return items.filter(function (el) { return !isInside(el, set); });  // outermost only
  }

  // Click "Show more" inside posts and "View more"/"Load more" at the end of the feed.
  var IN_POST = /^(show|see|view|read) (more|all|full (email|message))$|^more$|^expand( post| email)?$/i;
  var IN_FEED = /^(show|see|view|load) (more|all)( (posts|updates|feed items|activity|emails))?$/i;

  function clickMatching(scope, regex) {
    var n = 0;
    deepQueryAll(scope, 'button, a').forEach(function (b) {
      var t = (b.innerText || b.textContent || '').replace(/\s+/g, ' ').trim();
      if (t.length < 30 && regex.test(t) && !b.dataset.caseworkClicked && isVisible(b)) {
        b.dataset.caseworkClicked = '1';
        b.click();
        n++;
      }
    });
    return n;
  }

  async function expandFeed(maxRounds) {
    for (var round = 0; round < maxRounds; round++) {
      var items = visibleFeedItems();
      if (!items.length) return;
      var clicked = 0;
      items.forEach(function (it) { clicked += clickMatching(it, IN_POST); });
      var feed = items[0];  // climb a few levels to reach the feed list's "View more" button
      for (var i = 0; i < 4 && composedParent(feed) && composedParent(feed).nodeType === 1; i++) feed = composedParent(feed);
      clicked += clickMatching(feed, IN_FEED);
      if (!clicked) return;
      await sleep(1500);
    }
  }

  function readFields() {
    var fields = [], seen = new Set();
    deepQueryAll(document, FIELD_ITEM).filter(isVisible).forEach(function (item) {
      var labelEl = deepQuery(item, FIELD_LABEL);
      var label = labelEl ? deepText(labelEl) : '';
      var valueEl = deepQuery(item, FIELD_VALUE);
      var value = valueEl ? deepText(valueEl) : '';
      label = label.split('\n')[0].trim();
      if (!label) {
        var lines = deepText(item).split('\n').filter(Boolean);
        label = (lines.shift() || '').trim();
        value = value || lines.join('\n');
      } else if (valueEl && valueEl.contains(labelEl)) {
        value = value.slice(value.indexOf(label) + label.length).trim();  // value container also holds the label
      }
      if (!label || label.length > 80 || seen.has(label.toLowerCase())) return;
      seen.add(label.toLowerCase());
      fields.push({ label: label, value: value.slice(0, 20000) });
    });
    return fields;
  }

  function readFeed() {
    return visibleFeedItems().map(function (item) {
      var authorEl = deepQuery(item, FEED_AUTHOR);
      var timeEl = deepQuery(item, FEED_TIME);
      var timeTitle = '';
      if (timeEl) {
        timeTitle = timeEl.getAttribute('title') || timeEl.getAttribute('datetime') ||
                    timeEl.getAttribute('value') || '';
        var a = timeEl.closest && timeEl.closest('a[title]');
        if (!timeTitle && a) timeTitle = a.getAttribute('title');
      }
      return {
        author: authorEl ? deepText(authorEl).split('\n')[0] : '',
        timeText: timeEl ? deepText(timeEl) : '',
        timeTitle: timeTitle,
        text: deepText(item).slice(0, 100000)
      };
    });
  }

  function caseNumber(fields) {
    for (var i = 0; i < fields.length; i++) {
      if (/^case (number|no\.?|#)$/i.test(fields[i].label) && fields[i].value) return fields[i].value.split('\n')[0];
    }
    var m = (document.title || '').match(/\b(\d{5,})\b/);
    if (m) return m[1];
    var tabs = deepQueryAll(document, '[role="tab"][aria-selected="true"], .tabItem.active, li.slds-is-active');
    for (var j = 0; j < tabs.length; j++) {
      var t = deepText(tabs[j]).match(/\b(\d{5,})\b/);
      if (t) return t[1];
    }
    return '';
  }

  // Structure-only outline (tag + classes, no text) to help fix selectors without sharing case data.
  function outline(root, depth, maxDepth, out) {
    if (depth > maxDepth || out.length > 4000) return out;
    children(root).forEach(function (el) {
      if (!isVisible(el)) return;
      var cls = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/).slice(0, 4).join('.');
      out.push(new Array(depth + 1).join('  ') + el.tagName.toLowerCase() + (cls ? '.' + cls : '') +
               (el.shadowRoot ? ' #shadow' : ''));
      outline(el, depth + 1, maxDepth, out);
    });
    return out;
  }

  window.__caseworkExtract = async function (options) {
    options = options || {};
    var warnings = [];
    if (options.expand !== false) {
      try { await expandFeed(6); } catch (e) { warnings.push('Could not expand the feed: ' + e.message); }
    }
    var fields = readFields();
    var feed = readFeed();
    if (!fields.length) warnings.push('No case fields were found on the page.');
    if (!feed.length) warnings.push('No feed items were found. Open the case feed (All Updates) and try again.');
    var result = {
      source: 'salesforce-lightning',
      version: 1,
      url: location.href,
      title: document.title,
      capturedAt: new Date().toISOString(),
      userName: options.userName || '',
      caseNumber: caseNumber(fields),
      fields: fields,
      feed: feed,
      warnings: warnings
    };
    if (options.debug) {
      result.debug = {
        fieldItemCount: deepQueryAll(document, FIELD_ITEM).length,
        feedItemCandidates: deepQueryAll(document, FEED_ITEM).length,
        outline: outline(document.body, 0, 40, [])
      };
      result.fields = fields.map(function (f) { return { label: f.label, value: '(' + f.value.length + ' chars)' }; });
      result.feed = feed.map(function (f) {
        return { author: f.author ? '(author)' : '', timeText: f.timeText, timeTitle: f.timeTitle,
                 text: '(' + f.text.length + ' chars)' };
      });
    }
    return result;
  };
})();
```

#### `chrome-extension/popup.html`

The small window that opens when you click the extension icon.

```jinja
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Casework Capture</title><link rel="stylesheet" href="common.css">
<style>body { width: 320px; padding: 14px; } .small { font-size: 12px; } #debug { margin-top: 10px; }</style></head>
<body>
  <h1>Send case to Casework</h1>
  <p class="hint">Open a case in Salesforce with its feed showing (e.g. <em>All Updates</em>), then click Capture.</p>
  <label class="check"><input type="checkbox" id="expand" checked> Expand "show more" posts first</label>
  <div class="row" style="margin-top:10px">
    <button class="primary" id="capture">Capture this case</button>
    <a href="#" id="settings" class="small">Settings</a>
  </div>
  <div id="status" class="status"></div>
  <div class="row small" id="debug"><a href="#" id="debugBtn">Download page structure (no case data) for troubleshooting</a></div>
  <script src="popup.js"></script>
</body>
</html>
```

#### `chrome-extension/popup.js`

Runs the extractor on the current tab, sends the result to Casework, and opens the review page.

```
'use strict';
var statusEl = document.getElementById('status');

function show(msg, kind) {
  statusEl.textContent = msg;
  statusEl.className = 'status ' + (kind || '');
}

function getSettings() {
  return chrome.storage.local.get({ serverUrl: '', apiToken: '', userName: '' });
}

async function runExtractor(options) {
  var [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https:\/\//.test(tab.url || '')) throw new Error('Open the Salesforce case in this tab first.');
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['extractor.js'] });
  var [res] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: function (opts) { return window.__caseworkExtract(opts); },
    args: [options]
  });
  if (!res || !res.result) throw new Error('Could not read this page.');
  return res.result;
}

document.getElementById('settings').addEventListener('click', function (e) {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

document.getElementById('capture').addEventListener('click', async function () {
  var btn = this;
  btn.disabled = true;
  try {
    var s = await getSettings();
    if (!s.serverUrl) { show('Set your Casework server address in Settings first.', 'err'); return; }
    show('Reading the case…');
    var data = await runExtractor({ userName: s.userName, expand: document.getElementById('expand').checked });
    show('Found case ' + (data.caseNumber || '(no number)') + ': ' + data.fields.length + ' fields, ' +
         data.feed.length + ' feed items.\nSending to Casework…');
    var headers = { 'Content-Type': 'application/json' };
    if (s.apiToken) headers.Authorization = 'Bearer ' + s.apiToken;
    var resp = await fetch(s.serverUrl.replace(/\/+$/, '') + '/api/import', {
      method: 'POST', headers: headers, body: JSON.stringify(data)
    });
    var body = await resp.json().catch(function () { return {}; });
    if (!resp.ok || !body.ok) throw new Error(body.error || ('Server returned ' + resp.status));
    show('Sent. ' + body.counts.included + ' items suggested, ' + body.counts.ignored + ' ignored. Opening review…', 'ok');
    chrome.tabs.create({ url: body.reviewUrl });
  } catch (err) {
    var msg = err.message || String(err);
    if (/Failed to fetch/i.test(msg)) {
      msg = 'Could not reach the Casework server. Check the address in Settings, that the server is running, ' +
            'and (for HTTPS) that this PC trusts its certificate.';
    }
    show(msg, 'err');
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('debugBtn').addEventListener('click', async function (e) {
  e.preventDefault();
  try {
    var data = await runExtractor({ debug: true, expand: false });
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'casework-page-structure.json'; a.click();
    show('Saved casework-page-structure.json. It lists page element names and counts, not case text.', 'ok');
  } catch (err) {
    show(err.message || String(err), 'err');
  }
});
```

#### `chrome-extension/options.html`

The settings page: server address, API token, your name in Salesforce.

```jinja
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Casework Capture settings</title><link rel="stylesheet" href="common.css">
<style>body { max-width: 560px; padding: 24px; }</style></head>
<body>
  <h1>Casework Capture settings</h1>

  <label for="serverUrl">Casework server address</label>
  <input type="url" id="serverUrl" placeholder="http://127.0.0.1:5000 or https://casework.mycompany.local:8443">
  <div class="hint">The address you open Casework at, without anything after the port.</div>

  <label for="apiToken">API token</label>
  <input type="password" id="apiToken" autocomplete="off">
  <div class="hint">Must match <code>CASEWORK_API_TOKEN</code> on the server. Leave empty only if the server has no login.</div>

  <label for="userName">Your name as shown in Salesforce</label>
  <input type="text" id="userName" placeholder="e.g. Sathishkumar Ashok">
  <div class="hint">Used to tell your messages apart from the customer's. If empty, the Case Owner is used.</div>

  <div class="row" style="margin-top:16px">
    <button class="primary" id="save">Save</button>
    <button id="test">Test connection</button>
  </div>
  <div id="status" class="status"></div>
  <script src="options.js"></script>
</body>
</html>
```

#### `chrome-extension/options.js`

Saves the settings and tests the connection to Casework.

```
'use strict';
var $ = function (id) { return document.getElementById(id); };
var statusEl = $('status');

function show(msg, kind) { statusEl.textContent = msg; statusEl.className = 'status ' + (kind || ''); }

chrome.storage.local.get({ serverUrl: '', apiToken: '', userName: '' }).then(function (s) {
  $('serverUrl').value = s.serverUrl;
  $('apiToken').value = s.apiToken;
  $('userName').value = s.userName;
});

async function save() {
  var serverUrl = $('serverUrl').value.trim().replace(/\/+$/, '');
  try { new URL(serverUrl); } catch (e) { show('Enter a full address, e.g. http://127.0.0.1:5000', 'err'); return false; }
  await chrome.storage.local.set({
    serverUrl: serverUrl, apiToken: $('apiToken').value.trim(), userName: $('userName').value.trim()
  });
  $('serverUrl').value = serverUrl;
  show('Saved.', 'ok');
  return true;
}

$('save').addEventListener('click', save);

$('test').addEventListener('click', async function () {
  if (!(await save())) return;
  show('Testing…');
  try {
    var headers = {};
    var token = $('apiToken').value.trim();
    if (token) headers.Authorization = 'Bearer ' + token;
    var resp = await fetch($('serverUrl').value + '/api/ping', { headers: headers });
    var body = await resp.json().catch(function () { return {}; });
    if (resp.ok && body.ok) show('Connected to Casework.', 'ok');
    else show(body.error || ('Server returned ' + resp.status), 'err');
  } catch (e) {
    show('Could not reach the server. Check the address, that Casework is running, and (for HTTPS) that this PC trusts its certificate.', 'err');
  }
});
```

#### `chrome-extension/background.js`

Opens the settings page when the extension is first installed.

```
// Opens the settings page the first time the extension is installed.
chrome.runtime.onInstalled.addListener(function (details) {
  if (details.reason === 'install') chrome.runtime.openOptionsPage();
});
```

#### `chrome-extension/common.css`

Shared styling for the popup and settings page (follows Windows light/dark mode).

```css
:root { --fg: #1b1f24; --muted: #59636e; --bg: #ffffff; --line: #d1d9e0; --accent: #0b5cad; --ok: #1a7f37; --err: #cf222e; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #e6edf3; --muted: #9198a1; --bg: #151b23; --line: #3d444d; --accent: #4493f8; --ok: #3fb950; --err: #f85149; }
}
* { box-sizing: border-box; }
body { font: 14px/1.45 system-ui, "Segoe UI", sans-serif; color: var(--fg); background: var(--bg); margin: 0; }
h1 { font-size: 16px; margin: 0 0 8px; }
label { display: block; font-weight: 600; margin: 12px 0 4px; }
input[type=text], input[type=url], input[type=password] { width: 100%; padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); color: var(--fg); font: inherit; }
.hint { color: var(--muted); font-size: 12px; margin-top: 3px; }
button { font: inherit; padding: 7px 12px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); cursor: pointer; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
button:disabled { opacity: .6; cursor: default; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.status { margin-top: 10px; white-space: pre-wrap; }
.status.ok { color: var(--ok); } .status.err { color: var(--err); }
.check { display: flex; gap: 6px; align-items: center; font-weight: 400; }
a { color: var(--accent); }
```

**Icons.** Chrome needs three PNG icons. Create them with this one-off command (any
16x16, 48x48 and 128x128 PNGs named the same way also work):

```powershell
pip install pillow
python -c "from PIL import Image, ImageDraw; [ (lambda s: (lambda im: (ImageDraw.Draw(im).rounded_rectangle([0,0,s-1,s-1], radius=max(2,s//6), fill=(11,92,173,255)), im.save(f'chrome-extension/icons/icon{s}.png')))(Image.new('RGBA',(s,s))))(s) for s in (16,48,128)]"
```

**Tests.** Add the test for the importer and the sample capture it uses:


#### `tests/test_import.py`

Checks field mapping, feed sorting, date handling, the API, the review/apply flow and that re-capturing skips items already imported.

```python
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
```

`tests\fixtures\salesforce_capture.json` is a sample capture (what the extension produces).
Copy it from the repository, since it's data rather than code. Then run all tests again.

**Try it:** load the extension in Chrome and capture a case, following
[CHROME_EXTENSION.md](CHROME_EXTENSION.md) from step 2.

## 15. Save your work with Git

1. Open **Source Control** (**Ctrl+Shift+G**).
2. Check the list of changed files. `.venv`, `instance`, `certs` and `backups` should **not**
   appear; `.gitignore` excludes them.
3. Type a message such as `Casework app` and click **Commit**. If asked to stage all changes,
   click **Yes**.
4. To put it on GitHub: click **Publish Branch** (or **Publish to GitHub**) and follow the
   sign-in prompts. You can then `git clone` it onto your Windows Server.

## 16. Next steps

- **Deploy it:** follow [DEPLOY_WINDOWS.md](DEPLOY_WINDOWS.md) to run it as a service on
  Windows Server with HTTPS.
- **Change the thresholds:** set `CASEWORK_SWARM_AGE_DAYS` / `CASEWORK_SI_AGE_DAYS`
  environment variables (for example in the `"env"` block of `launch.json`).
- **Add a field to a tab:** add a column to `Entry` in `models.py`, add a line to that tab's
  `fields` in `entry_types.py`, and show it in the tab in `case_detail.html` (and in
  `reports.py` if it belongs in the reports).
  SQLite tables aren't updated automatically when you add a column, so either delete
  `instance\casework.db` while it only has test data, or add the column by hand.
- **Look inside the database:** install a SQLite viewer extension (search "SQLite" in
  Extensions) and open `instance\casework.db`.

## 17. Troubleshooting

| Problem | Fix |
|---|---|
| `python` opens the Microsoft Store | *Settings > Apps > Advanced app settings > App execution aliases*: turn off the two *python* entries, then reopen VS Code. |
| "running scripts is disabled on this system" | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then open a new terminal. |
| `ModuleNotFoundError: No module named 'flask'` | The wrong interpreter is selected. **Ctrl+Shift+P > Python: Select Interpreter** and choose the one in `.venv`, then `pip install -r requirements.txt` in a terminal that shows `(.venv)`. |
| `TemplateNotFound` | Templates must be in `casework\templates\` with the exact file names above. |
| `TemplateSyntaxError` | A block was pasted partially. Re-copy the whole file; the error shows the file and line. |
| Page has no styling or icons | The five Bootstrap files from step 9 are missing or in the wrong folder. |
| `Address already in use` / port 5000 busy | Stop the other server (**Shift+F5**), or change `--port` in `launch.json`. |
| Tests can't import `casework` | Make sure `pytest.ini` is in the project root and contains `pythonpath = .` |
| `HTTPS needs both CASEWORK_SSL_CERT and CASEWORK_SSL_KEY` | Run step 13.1 to create `certs\cert.pem` and `certs\key.pem`. |
| Changes don't show up | Restart the server (**Ctrl+Shift+F5**) after editing Python files or templates. |
