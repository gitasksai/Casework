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
