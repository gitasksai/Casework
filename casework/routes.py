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
