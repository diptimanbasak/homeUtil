"""
Car maintenance module: vehicles, their service history, and
upcoming-maintenance reminders. This is the first home-utility
module; future modules (e.g. appliances) should follow the same
shape -- a blueprint file per topic, registered in main.py.
"""
import datetime

from flask import Blueprint, abort, redirect, render_template, request
from sqlalchemy.orm import Session

from database import get_db
from models import MaintenanceRecord, MaintenanceReminder, Vehicle
from routes.dashboard import _reminder_status

bp = Blueprint("vehicles", __name__, url_prefix="/vehicles")

COMMON_SERVICE_TYPES = [
    "Oil Change", "Tire Rotation", "Tire Replacement",
    "Brake Inspection", "Brake Pad Replacement",
    "Air Filter Replacement", "Cabin Air Filter Replacement",
    "Spark Plug Replacement", "Battery Check", "Battery Replacement",
    "Coolant Flush", "Transmission Service", "Power Steering Fluid",
    "Brake Fluid Flush", "Fuel Filter", "Windshield Wiper Replacement",
    "Belt Replacement", "General Inspection", "Emission Test",
    "Registration Renewal", "Insurance Renewal",
    "Wheel Alignment", "Wheel Balancing", "A/C Service", "Other",
]


def get_vehicle_or_404(vehicle_id: int, db: Session) -> Vehicle:
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        abort(404, description="Vehicle not found")
    return vehicle


def resolve_service_type(service_type: str, custom_service_type: str) -> str:
    """If the user picked 'Other', use their free-text value instead."""
    if service_type == "Other" and custom_service_type.strip():
        return custom_service_type.strip()
    return service_type


def get_reminder_or_404(vehicle_id: int, reminder_id: int, db: Session) -> MaintenanceReminder:
    reminder = (
        db.query(MaintenanceReminder)
        .filter(MaintenanceReminder.id == reminder_id, MaintenanceReminder.vehicle_id == vehicle_id)
        .first()
    )
    if not reminder:
        abort(404, description="Reminder not found")
    return reminder


def reminder_type_fields(reminder: MaintenanceReminder):
    """Split a stored service_type back into (dropdown selection, custom text)."""
    if reminder.service_type in COMMON_SERVICE_TYPES:
        return reminder.service_type, ""
    return "Other", reminder.service_type


# ---------------------------------------------------------------- list/create

@bp.route("/")
def list_vehicles():
    db = get_db()
    today = datetime.date.today()
    vehicles = db.query(Vehicle).order_by(Vehicle.make, Vehicle.model).all()

    vehicle_data = []
    for v in vehicles:
        active_reminders = [r for r in v.reminders if not r.is_completed]
        statuses = [_reminder_status(r, v, today) for r in active_reminders]

        if "overdue" in statuses:
            overall_status = "overdue"
        elif "due_soon" in statuses:
            overall_status = "due_soon"
        else:
            overall_status = "ok"

        last_service = max(v.maintenance_records, key=lambda r: r.service_date, default=None)

        vehicle_data.append({
            "vehicle": v,
            "status": overall_status,
            "last_service": last_service,
            "active_reminder_count": len(active_reminders),
        })

    return render_template("vehicles/list.html", vehicle_data=vehicle_data)


@bp.route("/new", methods=["GET"])
def add_vehicle_form():
    return render_template("vehicles/add_vehicle.html", error=None)


@bp.route("/new", methods=["POST"])
def create_vehicle():
    db = get_db()
    nickname = request.form.get("nickname", "")
    make = request.form.get("make", "")
    model = request.form.get("model", "")
    year = request.form.get("year", type=int)
    license_plate = request.form.get("license_plate", "")
    vin = request.form.get("vin", "")
    color = request.form.get("color", "")
    current_mileage = request.form.get("current_mileage", 0, type=int)
    notes = request.form.get("notes", "")

    if not make.strip() or not model.strip():
        return render_template(
            "vehicles/add_vehicle.html", error="Make and Model are required."
        ), 400

    vehicle = Vehicle(
        nickname=nickname.strip() or None,
        make=make.strip(),
        model=model.strip(),
        year=year,
        license_plate=license_plate.strip() or None,
        vin=vin.strip() or None,
        color=color.strip() or None,
        current_mileage=current_mileage,
        notes=notes.strip() or None,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    return redirect(f"/vehicles/{vehicle.id}", code=303)


# ------------------------------------------------------------------- detail

@bp.route("/<int:vehicle_id>")
def vehicle_detail(vehicle_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)
    today = datetime.date.today()

    records = sorted(vehicle.maintenance_records, key=lambda r: r.service_date, reverse=True)

    active_reminders = [
        {"reminder": r, "status": _reminder_status(r, vehicle, today)}
        for r in vehicle.reminders
        if not r.is_completed
    ]
    status_order = {"overdue": 0, "due_soon": 1, "ok": 2}
    active_reminders.sort(key=lambda x: status_order[x["status"]])

    return render_template(
        "vehicles/detail.html",
        vehicle=vehicle,
        records=records,
        active_reminders=active_reminders,
    )


@bp.route("/<int:vehicle_id>/edit", methods=["GET"])
def edit_vehicle_form(vehicle_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)
    return render_template("vehicles/edit_vehicle.html", vehicle=vehicle, error=None)


@bp.route("/<int:vehicle_id>/edit", methods=["POST"])
def update_vehicle(vehicle_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)

    nickname = request.form.get("nickname", "")
    make = request.form.get("make", "")
    model = request.form.get("model", "")
    year = request.form.get("year", type=int)
    license_plate = request.form.get("license_plate", "")
    vin = request.form.get("vin", "")
    color = request.form.get("color", "")
    current_mileage = request.form.get("current_mileage", 0, type=int)
    notes = request.form.get("notes", "")

    if not make.strip() or not model.strip():
        return render_template(
            "vehicles/edit_vehicle.html",
            vehicle=vehicle,
            error="Make and Model are required.",
        ), 400

    vehicle.nickname = nickname.strip() or None
    vehicle.make = make.strip()
    vehicle.model = model.strip()
    vehicle.year = year
    vehicle.license_plate = license_plate.strip() or None
    vehicle.vin = vin.strip() or None
    vehicle.color = color.strip() or None
    vehicle.current_mileage = current_mileage
    vehicle.notes = notes.strip() or None

    db.commit()
    return redirect(f"/vehicles/{vehicle_id}", code=303)


@bp.route("/<int:vehicle_id>/delete", methods=["POST"])
def delete_vehicle(vehicle_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)
    db.delete(vehicle)
    db.commit()
    return redirect("/vehicles", code=303)


# -------------------------------------------------------------- service log

@bp.route("/<int:vehicle_id>/services/new", methods=["GET"])
def add_service_form(vehicle_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)
    return render_template(
        "vehicles/add_service.html",
        vehicle=vehicle,
        service_types=COMMON_SERVICE_TYPES,
        today=datetime.date.today().isoformat(),
        error=None,
    )


@bp.route("/<int:vehicle_id>/services/new", methods=["POST"])
def create_service_record(vehicle_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)

    service_type = request.form.get("service_type", "")
    custom_service_type = request.form.get("custom_service_type", "")
    service_date = request.form.get("service_date", "")
    mileage_at_service = request.form.get("mileage_at_service", type=int)
    cost = request.form.get("cost", type=float)
    service_provider = request.form.get("service_provider", "")
    notes = request.form.get("notes", "")

    try:
        date_obj = datetime.date.fromisoformat(service_date)
    except ValueError:
        return render_template(
            "vehicles/add_service.html",
            vehicle=vehicle,
            service_types=COMMON_SERVICE_TYPES,
            today=datetime.date.today().isoformat(),
            error="Invalid date format.",
        ), 400

    record = MaintenanceRecord(
        vehicle_id=vehicle_id,
        service_type=resolve_service_type(service_type, custom_service_type),
        service_date=date_obj,
        mileage_at_service=mileage_at_service,
        cost=cost,
        service_provider=service_provider.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(record)

    if mileage_at_service and mileage_at_service > (vehicle.current_mileage or 0):
        vehicle.current_mileage = mileage_at_service

    db.commit()
    return redirect(f"/vehicles/{vehicle_id}", code=303)


@bp.route("/<int:vehicle_id>/services/<int:service_id>/delete", methods=["POST"])
def delete_service_record(vehicle_id, service_id):
    db = get_db()
    record = (
        db.query(MaintenanceRecord)
        .filter(MaintenanceRecord.id == service_id, MaintenanceRecord.vehicle_id == vehicle_id)
        .first()
    )
    if not record:
        abort(404, description="Service record not found")
    db.delete(record)
    db.commit()
    return redirect(f"/vehicles/{vehicle_id}", code=303)


# ----------------------------------------------------------------- reminders

@bp.route("/<int:vehicle_id>/reminders/new", methods=["GET"])
def add_reminder_form(vehicle_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)
    return render_template(
        "vehicles/add_reminder.html",
        vehicle=vehicle,
        service_types=COMMON_SERVICE_TYPES,
        error=None,
    )


@bp.route("/<int:vehicle_id>/reminders/new", methods=["POST"])
def create_reminder(vehicle_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)

    service_type = request.form.get("service_type", "")
    custom_service_type = request.form.get("custom_service_type", "")
    due_date = request.form.get("due_date", "")
    due_mileage = request.form.get("due_mileage", type=int)
    notes = request.form.get("notes", "")

    date_obj = None
    if due_date.strip():
        try:
            date_obj = datetime.date.fromisoformat(due_date)
        except ValueError:
            return render_template(
                "vehicles/add_reminder.html",
                vehicle=vehicle,
                service_types=COMMON_SERVICE_TYPES,
                error="Invalid date format.",
            ), 400

    if not date_obj and not due_mileage:
        return render_template(
            "vehicles/add_reminder.html",
            vehicle=vehicle,
            service_types=COMMON_SERVICE_TYPES,
            error="Please provide at least a due date or due mileage.",
        ), 400

    reminder = MaintenanceReminder(
        vehicle_id=vehicle_id,
        service_type=resolve_service_type(service_type, custom_service_type),
        due_date=date_obj,
        due_mileage=due_mileage,
        notes=notes.strip() or None,
    )
    db.add(reminder)
    db.commit()
    return redirect(f"/vehicles/{vehicle_id}", code=303)


@bp.route("/<int:vehicle_id>/reminders/<int:reminder_id>/edit", methods=["GET"])
def edit_reminder_form(vehicle_id, reminder_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)
    reminder = get_reminder_or_404(vehicle_id, reminder_id, db)
    selected_type, custom_service_type = reminder_type_fields(reminder)

    return render_template(
        "vehicles/edit_reminder.html",
        vehicle=vehicle,
        reminder=reminder,
        service_types=COMMON_SERVICE_TYPES,
        selected_type=selected_type,
        custom_service_type=custom_service_type,
        error=None,
    )


@bp.route("/<int:vehicle_id>/reminders/<int:reminder_id>/edit", methods=["POST"])
def update_reminder(vehicle_id, reminder_id):
    db = get_db()
    vehicle = get_vehicle_or_404(vehicle_id, db)
    reminder = get_reminder_or_404(vehicle_id, reminder_id, db)

    service_type = request.form.get("service_type", "")
    custom_service_type = request.form.get("custom_service_type", "")
    due_date = request.form.get("due_date", "")
    due_mileage = request.form.get("due_mileage", type=int)
    notes = request.form.get("notes", "")

    def redisplay(error, status_code):
        selected_type, original_custom = reminder_type_fields(reminder)
        return render_template(
            "vehicles/edit_reminder.html",
            vehicle=vehicle,
            reminder=reminder,
            service_types=COMMON_SERVICE_TYPES,
            selected_type=selected_type,
            custom_service_type=original_custom,
            error=error,
        ), status_code

    date_obj = None
    if due_date.strip():
        try:
            date_obj = datetime.date.fromisoformat(due_date)
        except ValueError:
            return redisplay("Invalid date format.", 400)

    if not date_obj and not due_mileage:
        return redisplay("Please provide at least a due date or due mileage.", 400)

    reminder.service_type = resolve_service_type(service_type, custom_service_type)
    reminder.due_date = date_obj
    reminder.due_mileage = due_mileage
    reminder.notes = notes.strip() or None
    db.commit()
    return redirect(f"/vehicles/{vehicle_id}", code=303)


@bp.route("/<int:vehicle_id>/reminders/<int:reminder_id>/complete", methods=["POST"])
def complete_reminder(vehicle_id, reminder_id):
    db = get_db()
    reminder = get_reminder_or_404(vehicle_id, reminder_id, db)
    reminder.is_completed = True
    db.commit()
    return redirect(f"/vehicles/{vehicle_id}", code=303)


@bp.route("/<int:vehicle_id>/reminders/<int:reminder_id>/delete", methods=["POST"])
def delete_reminder(vehicle_id, reminder_id):
    db = get_db()
    reminder = get_reminder_or_404(vehicle_id, reminder_id, db)
    db.delete(reminder)
    db.commit()
    return redirect(f"/vehicles/{vehicle_id}", code=303)
