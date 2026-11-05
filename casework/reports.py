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
