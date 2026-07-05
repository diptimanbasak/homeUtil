"""
Data models for HomeUtil.

Each class here maps to one database table. Modules: vehicles (car
maintenance), chores (daily home chores tracking), expenses (receipt
tracking).
"""
import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Vehicle(Base):
    """A car, truck, or motorcycle being tracked."""

    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    nickname = Column(String(50))          # e.g. "Dad's car" -- optional friendly name
    make = Column(String(50), nullable=False)
    model = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    license_plate = Column(String(20))
    vin = Column(String(17))
    color = Column(String(30))
    current_mileage = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    maintenance_records = relationship(
        "MaintenanceRecord", back_populates="vehicle", cascade="all, delete-orphan"
    )
    reminders = relationship(
        "MaintenanceReminder", back_populates="vehicle", cascade="all, delete-orphan"
    )


class MaintenanceRecord(Base):
    """A completed service event, e.g. an oil change performed last month."""

    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    service_type = Column(String(100), nullable=False)   # "Oil Change", "Tire Rotation", ...
    service_date = Column(Date, nullable=False)
    mileage_at_service = Column(Integer)
    cost = Column(Float)
    service_provider = Column(String(100))                # "Jiffy Lube", "Home", ...
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="maintenance_records")


class MaintenanceReminder(Base):
    """A future service that hasn't happened yet, tracked by date and/or mileage."""

    __tablename__ = "maintenance_reminders"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    service_type = Column(String(100), nullable=False)
    last_service_date = Column(Date)
    due_date = Column(Date)
    due_mileage = Column(Integer)
    is_completed = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="reminders")


CHORE_FREQUENCIES = {
    "daily": 1,
    "every_other_day": 2,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
}

CHORE_CATEGORIES = [
    "Cleaning", "Laundry", "Kitchen", "Yard & Garden",
    "Groceries", "Pet Care", "Maintenance", "Other",
]


class Chore(Base):
    """A recurring household chore with a frequency-based schedule."""

    __tablename__ = "chores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), default="Other")
    frequency = Column(String(20), nullable=False, default="weekly")
    assigned_to = Column(String(100))
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    logs = relationship("ChoreLog", back_populates="chore", cascade="all, delete-orphan")

    @property
    def interval_days(self) -> int:
        return CHORE_FREQUENCIES.get(self.frequency, 7)

    def next_due(self) -> datetime.date:
        last = self.last_completed()
        base = last if last else self.created_at.date()
        return base + datetime.timedelta(days=self.interval_days)

    def last_completed(self):
        if not self.logs:
            return None
        return max(log.completed_on for log in self.logs)

    def status(self, today: datetime.date = None) -> str:
        today = today or datetime.date.today()
        due = self.next_due()
        if due < today:
            return "overdue"
        if due == today:
            return "due_today"
        return "ok"


class ChoreLog(Base):
    """A single completion event for a chore."""

    __tablename__ = "chore_logs"

    id = Column(Integer, primary_key=True, index=True)
    chore_id = Column(Integer, ForeignKey("chores.id"), nullable=False)
    completed_on = Column(Date, nullable=False)
    completed_by = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    chore = relationship("Chore", back_populates="logs")


EXPENSE_CATEGORIES = [
    "Groceries", "Dining", "Utilities", "Home", "Auto",
    "Medical", "Shopping", "Entertainment", "Electronics",
    "Home Repair", "Cleaning Supplies", "Decor", "Other",
]

# Vendor name (lowercase substring match) -> category. Applied on receipt
# scan, overriding whatever category Claude extracted, since the vendor
# itself is a stronger signal than per-receipt extraction for known stores.
VENDOR_CATEGORY_RULES = [
    ("patel brothers", "Groceries"),
]


def categorize_by_vendor(vendor: str | None) -> str | None:
    if not vendor:
        return None
    vendor_lower = vendor.lower()
    for needle, category in VENDOR_CATEGORY_RULES:
        if needle in vendor_lower:
            return category
    return None


# Fixed category -> color mapping (dataviz skill's 8-hue categorical
# palette), reused for badges across the expenses UI and the report's pie
# chart so a given category always reads as the same color everywhere.
# There are more categories than hues, so the palette repeats -- fine here
# since this is a UI accent, not a chart legend that needs every slice
# distinguishable at once.
_CATEGORY_PALETTE = [
    "#2a78d6", "#1baf7a", "#eda100", "#008300",
    "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
]
CATEGORY_COLORS = {
    cat: _CATEGORY_PALETTE[i % len(_CATEGORY_PALETTE)] for i, cat in enumerate(EXPENSE_CATEGORIES)
}


class Expense(Base):
    """A tracked expense, usually populated from a scanned receipt photo."""

    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    vendor = Column(String(150))
    amount = Column(Float)
    expense_date = Column(Date)
    category = Column(String(50), default="Other")
    receipt_filename = Column(String(255))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    items = relationship("ExpenseItem", back_populates="expense", cascade="all, delete-orphan")
    returned_items = relationship(
        "ReturnedItem", back_populates="expense", cascade="all, delete-orphan"
    )

    @property
    def net_amount(self):
        if self.amount is None:
            return None
        return self.amount - sum(ri.amount for ri in self.returned_items)

    @property
    def category_label(self):
        """Display label for the category column -- combines distinct item
        categories (e.g. "Groceries+Cleaning Supplies") for receipts that
        span more than one, since self.category alone only holds the
        single top-level category picked at scan time."""
        if not self.items:
            return self.category
        seen = []
        for item in self.items:
            cat = item.category or "Other"
            if cat not in seen:
                seen.append(cat)
        return "+".join(seen) if seen else self.category


class ExpenseItem(Base):
    """A single line item read off a receipt, e.g. 'Milk -- $3.49'."""

    __tablename__ = "expense_items"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    name = Column(String(200), nullable=False)
    price = Column(Float)
    category = Column(String(50), default="Other")

    expense = relationship("Expense", back_populates="items")


class ReturnedItem(Base):
    """An item from an expense that was later returned, reducing the net spend."""

    __tablename__ = "returned_items"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    name = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    returned_on = Column(Date, default=datetime.date.today)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    expense = relationship("Expense", back_populates="returned_items")
