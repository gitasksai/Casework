# Casework

A small Flask app for tracking day-to-day support case work, and for turning everything
you've logged into a **Swarm request** (case age 5+ days) or a **Structured Investigation**
write-up (case age 15+ days).

## Features

- **Cases**: case number, title, customer, product, version, operating system, severity,
  status, opened/closed dates, plus narrative fields (problem description, business impact,
  current status, next steps, help needed) that feed the reports.
- **Case page tabs**
  - **Overview**: all case fields at a glance
  - **Initial Response**: what you sent on first contact
  - **Scoping Q&A**: question / customer response pairs, with unanswered ones highlighted and
    a one-click "add standard scoping questions" button
  - **Troubleshooting**: session notes with actions taken, findings, next steps and duration
  - **Meeting Summaries**: attendees, summary, action items
  - **Other Notes**: anything else important
  - **Timeline**: everything in date order with its case day number
  - **Swarm / Investigation**: age progress bar, report buttons, and a readiness check that
    lists gaps a reviewer will ask about
- **Dashboard**: open cases with age badges (green, yellow = swarm due, red = structured
  investigation due), counts, search and status filter.
- **Reports**: generated as Markdown; copy to clipboard, download as `.md`, or print.
  - *Swarm request*: case summary, problem, impact, the ask, initial response, scoping,
    every troubleshooting session, meetings, notes, a **day-by-day activity log**,
    current status, next steps, gaps.
  - *Structured investigation*: executive summary, case details, problem statement,
    environment, escalation history, chronological timeline table, scoping, work completed,
    consolidated key findings, meetings and consolidated action items, notes, day-by-day log,
    gaps and open questions, status, next steps, and the investigation ask.

Case age is counted from the **Opened on** date (so you can back-date cases you're entering
late). Closed cases stop ageing at their closed date.

## Running

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py                     # optional: loads 3 sample cases (2, 6 and 17 days old)
python run.py                      # http://127.0.0.1:5000
```

Data is stored in SQLite at `instance/casework.db`.

## Capturing cases from Salesforce

The **Chrome extension** in `chrome-extension/` reads the Salesforce case you have open and sends
it to Casework. Casework sorts the case feed into the tabs, ignores follow-ups, acknowledgements
and automated posts, and shows a review screen before anything is saved. See
**[docs/CHROME_EXTENSION.md](docs/CHROME_EXTENSION.md)**.

## Building it yourself

[docs/BUILD_FROM_SCRATCH_VSCODE.md](docs/BUILD_FROM_SCRATCH_VSCODE.md) walks through creating
the whole app file by file in Visual Studio Code. The `.vscode/` folder has ready-made
Run and Debug configurations (dev server, HTTPS server, sample data, certificate).

## Deploying on Windows Server

See **[docs/DEPLOY_WINDOWS.md](docs/DEPLOY_WINDOWS.md)** for running it as a Windows service
with HTTPS served directly by Python (`python serve.py`, no IIS needed), a login, a
certificate helper (`python tls_cert.py`), firewall, and daily backups (`python backup.py`).

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `CASEWORK_SWARM_AGE_DAYS` | `5` | Age at which a swarm is due |
| `CASEWORK_SI_AGE_DAYS` | `15` | Age at which a structured investigation is due |
| `CASEWORK_DATABASE_URL` | `sqlite:///instance/casework.db` | SQLAlchemy database URL |
| `CASEWORK_SECRET_KEY` | `dev-change-me` | Flask session secret (set this if you host it) |
| `CASEWORK_USERNAME` / `CASEWORK_PASSWORD` | *(unset)* | When both are set, every page requires this login |
| `CASEWORK_API_TOKEN` | *(unset)* | Token the Chrome extension sends; required when a login is set |
| `CASEWORK_SSL_CERT` / `CASEWORK_SSL_KEY` | *(unset)* | PEM certificate and key; when set, `serve.py` serves HTTPS |
| `CASEWORK_HOST` / `CASEWORK_PORT` | `0.0.0.0` / `8443` (HTTPS) or `8080` | Where `serve.py` listens |

## Tests

```bash
pytest
```

## Note

Without `CASEWORK_USERNAME`/`CASEWORK_PASSWORD` there is no login, so set them before
exposing it on a network. The login is HTTP Basic auth, so also set
`CASEWORK_SSL_CERT`/`CASEWORK_SSL_KEY` to encrypt the connection. Bootstrap is bundled in `casework/static/vendor`, so no
internet access is needed.
