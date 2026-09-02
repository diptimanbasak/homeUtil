"""Filter Maintenance module: tracking HVAC and Air Purifier filter changes."""
import datetime

from flask import Blueprint, abort, redirect, render_template, request
from sqlalchemy.orm import Session

from database import get_db
from models import FILTER_KINDS, FILTER_TYPES, FilterRecord

bp = Blueprint("filter_maintenance", __name__, url_prefix="/filter-maintenance")


def get_filter_record_or_404(record_id: int, db: Session) -> FilterRecord:
    record = db.query(FilterRecord).filter(FilterRecord.id == record_id).first()
    if not record:
        abort(404, description="Filter record not found")
    return record


def _parse_date(value: str):
    """Returns (date_or_None, error_or_None)."""
    if not value.strip():
        return None, None
    try:
        return datetime.date.fromisoformat(value), None
    except ValueError:
        return None, "invalid"


# ------------------------------------------------------------------ list

@bp.route("/")
def list_filter_records():
    db = get_db()
    filter_type = request.args.get("filter_type", "")

    query = db.query(FilterRecord)
    if filter_type in FILTER_TYPES:
        query = query.filter(FilterRecord.filter_type == filter_type)
    records = query.order_by(FilterRecord.due_date.asc().nullslast()).all()

    return render_template(
        "filter_maintenance/list.html",
        records=records,
        filter_types=FILTER_TYPES,
        selected_type=filter_type,
    )


# ------------------------------------------------------------------ create

@bp.route("/new", methods=["GET"])
def add_filter_record_form():
    return render_template(
        "filter_maintenance/add_record.html",
        filter_types=FILTER_TYPES,
        filter_kinds=FILTER_KINDS,
        error=None,
    )


@bp.route("/new", methods=["POST"])
def create_filter_record():
    db = get_db()
    filter_type = request.form.get("filter_type", "")
    brand = request.form.get("brand", "")
    filter_kind = request.form.get("filter_kind", "")
    model = request.form.get("model", "")
    changed_on = request.form.get("changed_on", "")
    due_date = request.form.get("due_date", "")
    size = request.form.get("size", "")
    in_stock = request.form.get("in_stock") == "on"

    def render_error(message):
        return render_template(
            "filter_maintenance/add_record.html",
            filter_types=FILTER_TYPES,
            filter_kinds=FILTER_KINDS,
            error=message,
        ), 400

    if filter_type not in FILTER_TYPES:
        return render_error("Please select a valid filter type.")
    if filter_type == "Air Purifier" and filter_kind not in FILTER_KINDS:
        return render_error("Please select a valid filter kind (HEPA or Carbon).")

    changed_on_obj, err = _parse_date(changed_on)
    if err:
        return render_error("Please provide a valid Change Date.")
    due_date_obj, err = _parse_date(due_date)
    if err:
        return render_error("Please provide a valid Due Date.")

    record = FilterRecord(
        filter_type=filter_type,
        changed_on=changed_on_obj,
        due_date=due_date_obj,
        brand=brand.strip() or None if filter_type == "HVAC" else None,
        size=size.strip() or None if filter_type == "HVAC" else None,
        filter_kind=filter_kind if filter_type == "Air Purifier" else None,
        in_stock=in_stock if filter_type == "Air Purifier" else False,
        model=model.strip() or None if filter_type == "Air Purifier" else None,
    )
    db.add(record)
    db.commit()
    return redirect("/filter-maintenance", code=303)


# ------------------------------------------------------------------ edit

@bp.route("/<int:record_id>/edit", methods=["GET"])
def edit_filter_record_form(record_id):
    db = get_db()
    record = get_filter_record_or_404(record_id, db)
    return render_template(
        "filter_maintenance/edit_record.html",
        record=record,
        filter_types=FILTER_TYPES,
        filter_kinds=FILTER_KINDS,
        error=None,
    )


@bp.route("/<int:record_id>/edit", methods=["POST"])
def update_filter_record(record_id):
    db = get_db()
    record = get_filter_record_or_404(record_id, db)

    filter_type = request.form.get("filter_type", "")
    brand = request.form.get("brand", "")
    filter_kind = request.form.get("filter_kind", "")
    model = request.form.get("model", "")
    changed_on = request.form.get("changed_on", "")
    due_date = request.form.get("due_date", "")
    size = request.form.get("size", "")
    in_stock = request.form.get("in_stock") == "on"

    def render_error(message):
        return render_template(
            "filter_maintenance/edit_record.html",
            record=record,
            filter_types=FILTER_TYPES,
            filter_kinds=FILTER_KINDS,
            error=message,
        ), 400

    if filter_type not in FILTER_TYPES:
        return render_error("Please select a valid filter type.")
    if filter_type == "Air Purifier" and filter_kind not in FILTER_KINDS:
        return render_error("Please select a valid filter kind (HEPA or Carbon).")

    changed_on_obj, err = _parse_date(changed_on)
    if err:
        return render_error("Please provide a valid Change Date.")
    due_date_obj, err = _parse_date(due_date)
    if err:
        return render_error("Please provide a valid Due Date.")

    record.filter_type = filter_type
    record.changed_on = changed_on_obj
    record.due_date = due_date_obj
    record.brand = brand.strip() or None if filter_type == "HVAC" else None
    record.size = size.strip() or None if filter_type == "HVAC" else None
    record.filter_kind = filter_kind if filter_type == "Air Purifier" else None
    record.in_stock = in_stock if filter_type == "Air Purifier" else False
    record.model = model.strip() or None if filter_type == "Air Purifier" else None
    db.commit()
    return redirect("/filter-maintenance", code=303)


# ------------------------------------------------------------------ delete

@bp.route("/<int:record_id>/delete", methods=["POST"])
def delete_filter_record(record_id):
    db = get_db()
    record = get_filter_record_or_404(record_id, db)
    db.delete(record)
    db.commit()
    return redirect("/filter-maintenance", code=303)
