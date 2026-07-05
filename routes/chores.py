"""Chores module: daily/recurring household task tracking."""
import datetime

from flask import Blueprint, abort, redirect, render_template, request
from sqlalchemy.orm import Session

from database import get_db
from models import CHORE_CATEGORIES, CHORE_FREQUENCIES, Chore, ChoreLog

bp = Blueprint("chores", __name__, url_prefix="/chores")

FREQUENCY_LABELS = {
    "daily": "Daily",
    "every_other_day": "Every Other Day",
    "weekly": "Weekly",
    "biweekly": "Every 2 Weeks",
    "monthly": "Monthly",
}


def get_chore_or_404(chore_id: int, db: Session) -> Chore:
    chore = db.query(Chore).filter(Chore.id == chore_id).first()
    if not chore:
        abort(404, description="Chore not found")
    return chore


# ------------------------------------------------------------------ list

@bp.route("/")
def list_chores():
    db = get_db()
    today = datetime.date.today()
    chores = (
        db.query(Chore)
        .filter(Chore.is_active == True)  # noqa: E712
        .order_by(Chore.name)
        .all()
    )

    chore_data = []
    for c in chores:
        chore_data.append({
            "chore": c,
            "status": c.status(today),
            "next_due": c.next_due(),
            "last_completed": c.last_completed(),
            "frequency_label": FREQUENCY_LABELS.get(c.frequency, c.frequency),
        })

    status_order = {"overdue": 0, "due_today": 1, "ok": 2}
    chore_data.sort(key=lambda x: (status_order[x["status"]], x["next_due"]))

    overdue_count = sum(1 for c in chore_data if c["status"] == "overdue")
    due_today_count = sum(1 for c in chore_data if c["status"] == "due_today")

    return render_template(
        "chores/list.html",
        chore_data=chore_data,
        today=today,
        overdue_count=overdue_count,
        due_today_count=due_today_count,
    )


# ------------------------------------------------------------------ create

@bp.route("/new", methods=["GET"])
def add_chore_form():
    return render_template(
        "chores/add_chore.html",
        categories=CHORE_CATEGORIES,
        frequencies=FREQUENCY_LABELS,
        error=None,
    )


@bp.route("/new", methods=["POST"])
def create_chore():
    db = get_db()
    name = request.form.get("name", "")
    category = request.form.get("category", "Other")
    frequency = request.form.get("frequency", "weekly")
    assigned_to = request.form.get("assigned_to", "")
    notes = request.form.get("notes", "")

    if not name.strip():
        return render_template(
            "chores/add_chore.html",
            categories=CHORE_CATEGORIES,
            frequencies=FREQUENCY_LABELS,
            error="Chore name is required.",
        ), 400

    chore = Chore(
        name=name.strip(),
        category=category,
        frequency=frequency if frequency in CHORE_FREQUENCIES else "weekly",
        assigned_to=assigned_to.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(chore)
    db.commit()
    db.refresh(chore)
    return redirect("/chores", code=303)


# ------------------------------------------------------------------ detail

@bp.route("/<int:chore_id>")
def chore_detail(chore_id):
    db = get_db()
    chore = get_chore_or_404(chore_id, db)
    today = datetime.date.today()
    logs = sorted(chore.logs, key=lambda l: l.completed_on, reverse=True)
    return render_template(
        "chores/detail.html",
        chore=chore,
        status=chore.status(today),
        next_due=chore.next_due(),
        last_completed=chore.last_completed(),
        frequency_label=FREQUENCY_LABELS.get(chore.frequency, chore.frequency),
        logs=logs,
        today=today.isoformat(),
    )


# ------------------------------------------------------------------ edit

@bp.route("/<int:chore_id>/edit", methods=["GET"])
def edit_chore_form(chore_id):
    db = get_db()
    chore = get_chore_or_404(chore_id, db)
    return render_template(
        "chores/edit_chore.html",
        chore=chore,
        categories=CHORE_CATEGORIES,
        frequencies=FREQUENCY_LABELS,
        error=None,
    )


@bp.route("/<int:chore_id>/edit", methods=["POST"])
def update_chore(chore_id):
    db = get_db()
    chore = get_chore_or_404(chore_id, db)

    name = request.form.get("name", "")
    category = request.form.get("category", "Other")
    frequency = request.form.get("frequency", "weekly")
    assigned_to = request.form.get("assigned_to", "")
    notes = request.form.get("notes", "")

    if not name.strip():
        return render_template(
            "chores/edit_chore.html",
            chore=chore,
            categories=CHORE_CATEGORIES,
            frequencies=FREQUENCY_LABELS,
            error="Chore name is required.",
        ), 400

    chore.name = name.strip()
    chore.category = category
    chore.frequency = frequency if frequency in CHORE_FREQUENCIES else "weekly"
    chore.assigned_to = assigned_to.strip() or None
    chore.notes = notes.strip() or None
    db.commit()
    return redirect(f"/chores/{chore_id}", code=303)


@bp.route("/<int:chore_id>/deactivate", methods=["POST"])
def deactivate_chore(chore_id):
    db = get_db()
    chore = get_chore_or_404(chore_id, db)
    chore.is_active = False
    db.commit()
    return redirect("/chores", code=303)


# ------------------------------------------------------------------ log completion

@bp.route("/<int:chore_id>/complete", methods=["POST"])
def log_completion(chore_id):
    db = get_db()
    chore = get_chore_or_404(chore_id, db)

    completed_on = request.form.get("completed_on", "")
    completed_by = request.form.get("completed_by", "")
    notes = request.form.get("notes", "")

    if completed_on.strip():
        try:
            date_obj = datetime.date.fromisoformat(completed_on)
        except ValueError:
            date_obj = datetime.date.today()
    else:
        date_obj = datetime.date.today()

    log = ChoreLog(
        chore_id=chore_id,
        completed_on=date_obj,
        completed_by=completed_by.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(log)
    db.commit()
    return redirect("/chores", code=303)


@bp.route("/<int:chore_id>/logs/<int:log_id>/delete", methods=["POST"])
def delete_log(chore_id, log_id):
    db = get_db()
    log = (
        db.query(ChoreLog)
        .filter(ChoreLog.id == log_id, ChoreLog.chore_id == chore_id)
        .first()
    )
    if not log:
        abort(404, description="Log entry not found")
    db.delete(log)
    db.commit()
    return redirect(f"/chores/{chore_id}", code=303)
