"""Kids Classes module: tracking recurring kids' classes/activities."""
import datetime

from flask import Blueprint, abort, redirect, render_template, request
from sqlalchemy.orm import Session

from database import get_db
from models import KidsClass

bp = Blueprint("kids_classes", __name__, url_prefix="/kids-classes")


def get_kids_class_or_404(class_id: int, db: Session) -> KidsClass:
    kids_class = db.query(KidsClass).filter(KidsClass.id == class_id).first()
    if not kids_class:
        abort(404, description="Class not found")
    return kids_class


# ------------------------------------------------------------------ list

@bp.route("/")
def list_kids_classes():
    db = get_db()
    classes = db.query(KidsClass).order_by(KidsClass.class_date.desc().nullslast()).all()
    return render_template("kids_classes/list.html", classes=classes)


# ------------------------------------------------------------------ create

@bp.route("/new", methods=["GET"])
def add_kids_class_form():
    return render_template("kids_classes/add_class.html", error=None)


@bp.route("/new", methods=["POST"])
def create_kids_class():
    db = get_db()
    class_name = request.form.get("class_name", "")
    class_date = request.form.get("class_date", "")
    recurrence = request.form.get("recurrence", "")
    class_time = request.form.get("class_time", "")
    cost_details = request.form.get("cost_details", "")

    if not class_name.strip():
        return render_template(
            "kids_classes/add_class.html", error="Class Name is required."
        ), 400

    date_obj = None
    if class_date.strip():
        try:
            date_obj = datetime.date.fromisoformat(class_date)
        except ValueError:
            return render_template(
                "kids_classes/add_class.html", error="Please provide a valid date."
            ), 400

    kids_class = KidsClass(
        class_name=class_name.strip(),
        class_date=date_obj,
        recurrence=recurrence.strip() or None,
        class_time=class_time.strip() or None,
        cost_details=cost_details.strip() or None,
    )
    db.add(kids_class)
    db.commit()
    return redirect("/kids-classes", code=303)


# ------------------------------------------------------------------ edit

@bp.route("/<int:class_id>/edit", methods=["GET"])
def edit_kids_class_form(class_id):
    db = get_db()
    kids_class = get_kids_class_or_404(class_id, db)
    return render_template("kids_classes/edit_class.html", kids_class=kids_class, error=None)


@bp.route("/<int:class_id>/edit", methods=["POST"])
def update_kids_class(class_id):
    db = get_db()
    kids_class = get_kids_class_or_404(class_id, db)

    class_name = request.form.get("class_name", "")
    class_date = request.form.get("class_date", "")
    recurrence = request.form.get("recurrence", "")
    class_time = request.form.get("class_time", "")
    cost_details = request.form.get("cost_details", "")

    if not class_name.strip():
        return render_template(
            "kids_classes/edit_class.html",
            kids_class=kids_class,
            error="Class Name is required.",
        ), 400

    date_obj = None
    if class_date.strip():
        try:
            date_obj = datetime.date.fromisoformat(class_date)
        except ValueError:
            return render_template(
                "kids_classes/edit_class.html",
                kids_class=kids_class,
                error="Please provide a valid date.",
            ), 400

    kids_class.class_name = class_name.strip()
    kids_class.class_date = date_obj
    kids_class.recurrence = recurrence.strip() or None
    kids_class.class_time = class_time.strip() or None
    kids_class.cost_details = cost_details.strip() or None
    db.commit()
    return redirect("/kids-classes", code=303)


# ------------------------------------------------------------------ delete

@bp.route("/<int:class_id>/delete", methods=["POST"])
def delete_kids_class(class_id):
    db = get_db()
    kids_class = get_kids_class_or_404(class_id, db)
    db.delete(kids_class)
    db.commit()
    return redirect("/kids-classes", code=303)
