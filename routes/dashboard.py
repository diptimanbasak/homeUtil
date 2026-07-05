"""Home page: a quick-glance summary across all tracked vehicles and chores."""
import datetime

from flask import Blueprint, render_template
from sqlalchemy.orm import joinedload

from config import REMINDER_DUE_SOON_DAYS, REMINDER_DUE_SOON_MILES
from database import get_db
from models import Chore, MaintenanceRecord, Vehicle

bp = Blueprint("dashboard", __name__)


def _reminder_status(reminder, vehicle, today) -> str:
    """Classify a reminder as 'overdue', 'due_soon', or 'ok'."""
    soon_threshold = today + datetime.timedelta(days=REMINDER_DUE_SOON_DAYS)
    status = "ok"

    if reminder.due_date:
        if reminder.due_date < today:
            return "overdue"
        if reminder.due_date <= soon_threshold:
            status = "due_soon"

    if reminder.due_mileage and vehicle.current_mileage:
        miles_remaining = reminder.due_mileage - vehicle.current_mileage
        if miles_remaining <= 0:
            return "overdue"
        if miles_remaining <= REMINDER_DUE_SOON_MILES and status != "overdue":
            status = "due_soon"

    return status


@bp.route("/")
def dashboard():
    db = get_db()
    today = datetime.date.today()
    vehicles = db.query(Vehicle).all()

    overdue, due_soon = [], []
    for vehicle in vehicles:
        for reminder in vehicle.reminders:
            if reminder.is_completed:
                continue
            status = _reminder_status(reminder, vehicle, today)
            if status == "overdue":
                overdue.append({"vehicle": vehicle, "reminder": reminder})
            elif status == "due_soon":
                due_soon.append({"vehicle": vehicle, "reminder": reminder})

    recent_services = (
        db.query(MaintenanceRecord)
        .options(joinedload(MaintenanceRecord.vehicle))
        .order_by(MaintenanceRecord.service_date.desc())
        .limit(5)
        .all()
    )

    active_chores = db.query(Chore).filter(Chore.is_active == True).all()  # noqa: E712
    chores_overdue = [c for c in active_chores if c.status(today) == "overdue"]
    chores_due_today = [c for c in active_chores if c.status(today) == "due_today"]

    return render_template(
        "dashboard.html",
        vehicles=vehicles,
        overdue=overdue,
        due_soon=due_soon,
        recent_services=recent_services,
        chores_overdue=chores_overdue,
        chores_due_today=chores_due_today,
    )
