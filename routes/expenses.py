"""Expenses module: track spending by scanning receipt photos."""
import datetime
import math
import uuid
from collections import defaultdict

import pytesseract
from flask import Blueprint, abort, redirect, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from config import RECEIPTS_DIR
from database import get_db
from models import CATEGORY_COLORS, EXPENSE_CATEGORIES, Expense, ExpenseItem, ReturnedItem, categorize_by_vendor
from receipts import convert_heic_to_jpeg, extract_receipt_data

bp = Blueprint("expenses", __name__, url_prefix="/expenses")

RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


def get_expense_or_404(expense_id: int, db) -> Expense:
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        abort(404, description="Expense not found")
    return expense


# ------------------------------------------------------------------ list

@bp.route("/")
def list_expenses():
    db = get_db()
    expenses = db.query(Expense).order_by(Expense.expense_date.desc().nullslast()).all()
    total = sum(e.amount for e in expenses if e.amount)
    return render_template("expenses/list.html", expenses=expenses, total=total)


# ------------------------------------------------------------------ upload + analyze

@bp.route("/new", methods=["GET"])
def add_expense_form():
    return render_template("expenses/add_expense.html", error=None)


@bp.route("/new", methods=["POST"])
def create_expense():
    db = get_db()
    photo = request.files.get("receipt")

    if not photo or not photo.filename:
        return render_template(
            "expenses/add_expense.html", error="Please choose a receipt photo."
        ), 400

    image_bytes = photo.read()
    media_type = photo.mimetype or "image/jpeg"
    ext = secure_filename(photo.filename).rsplit(".", 1)[-1].lower() or "jpg"

    if ext == "pdf":
        media_type = "application/pdf"
    elif ext in ("heic", "heif"):
        image_bytes = convert_heic_to_jpeg(image_bytes)
        media_type = "image/jpeg"
        ext = "jpg"

    method = request.form.get("method", "anthropic")
    if method not in ("anthropic", "ocr"):
        method = "anthropic"

    try:
        extracted = extract_receipt_data(image_bytes, media_type, method=method)
    except pytesseract.TesseractNotFoundError:
        extracted = {"vendor": None, "amount": None, "expense_date": None, "category": None, "line_items": []}

    receipt_filename = f"{uuid.uuid4().hex}.{ext}"
    (RECEIPTS_DIR / receipt_filename).write_bytes(image_bytes)

    date_obj = None
    if extracted["expense_date"]:
        try:
            date_obj = datetime.date.fromisoformat(extracted["expense_date"])
        except ValueError:
            date_obj = None

    vendor_category = categorize_by_vendor(extracted["vendor"])
    category = vendor_category or (
        extracted["category"] if extracted["category"] in EXPENSE_CATEGORIES else "Other"
    )

    expense = Expense(
        vendor=extracted["vendor"],
        amount=extracted["amount"],
        expense_date=date_obj,
        category=category,
        receipt_filename=receipt_filename,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    for item in extracted["line_items"]:
        if item.get("name"):
            item_category = item.get("category")
            db.add(ExpenseItem(
                expense_id=expense.id,
                name=item["name"],
                price=item.get("price"),
                category=item_category if item_category in EXPENSE_CATEGORIES else "Other",
            ))
    db.commit()

    return redirect(f"/expenses/{expense.id}", code=303)


# ------------------------------------------------------------------- detail

@bp.route("/<int:expense_id>")
def expense_detail(expense_id):
    db = get_db()
    expense = get_expense_or_404(expense_id, db)
    return render_template("expenses/detail.html", expense=expense, categories=EXPENSE_CATEGORIES)


@bp.route("/<int:expense_id>/receipt")
def expense_receipt(expense_id):
    db = get_db()
    expense = get_expense_or_404(expense_id, db)
    if not expense.receipt_filename:
        abort(404)
    return send_from_directory(RECEIPTS_DIR, expense.receipt_filename)


@bp.route("/<int:expense_id>/edit", methods=["GET"])
def edit_expense_form(expense_id):
    db = get_db()
    expense = get_expense_or_404(expense_id, db)
    return render_template(
        "expenses/edit_expense.html",
        expense=expense,
        categories=EXPENSE_CATEGORIES,
        error=None,
    )


@bp.route("/<int:expense_id>/edit", methods=["POST"])
def update_expense(expense_id):
    db = get_db()
    expense = get_expense_or_404(expense_id, db)

    vendor = request.form.get("vendor", "")
    amount = request.form.get("amount", type=float)
    expense_date = request.form.get("expense_date", "")
    category = request.form.get("category", "Other")
    notes = request.form.get("notes", "")

    date_obj = None
    if expense_date.strip():
        try:
            date_obj = datetime.date.fromisoformat(expense_date)
        except ValueError:
            return render_template(
                "expenses/edit_expense.html",
                expense=expense,
                categories=EXPENSE_CATEGORIES,
                error="Invalid date format.",
            ), 400

    expense.vendor = vendor.strip() or None
    expense.amount = amount
    expense.expense_date = date_obj
    expense.category = category if category in EXPENSE_CATEGORIES else "Other"
    expense.notes = notes.strip() or None
    db.commit()
    return redirect(f"/expenses/{expense_id}", code=303)


@bp.route("/<int:expense_id>/delete", methods=["POST"])
def delete_expense(expense_id):
    db = get_db()
    expense = get_expense_or_404(expense_id, db)
    if expense.receipt_filename:
        (RECEIPTS_DIR / expense.receipt_filename).unlink(missing_ok=True)
    db.delete(expense)
    db.commit()
    return redirect("/expenses", code=303)


# --------------------------------------------------------------- line items

# Lets the user fix a per-item category from the detail page (e.g. Claude
# tagged an item wrong on scan) without having to edit the whole expense.
@bp.route("/<int:expense_id>/items/<int:item_id>/category", methods=["POST"])
def update_item_category(expense_id, item_id):
    db = get_db()
    get_expense_or_404(expense_id, db)
    item = (
        db.query(ExpenseItem)
        .filter(ExpenseItem.id == item_id, ExpenseItem.expense_id == expense_id)
        .first()
    )
    if not item:
        abort(404, description="Item not found")
    category = request.form.get("category", "Other")
    item.category = category if category in EXPENSE_CATEGORIES else "Other"
    db.commit()
    return redirect(f"/expenses/{expense_id}", code=303)


# ------------------------------------------------------------- returns flow

# Returns are tracked separately from expense items (rather than deleting/
# editing the item) so the original receipt data stays intact for reference.
@bp.route("/<int:expense_id>/returns", methods=["POST"])
def add_returned_item(expense_id):
    db = get_db()
    get_expense_or_404(expense_id, db)

    name = request.form.get("name", "").strip()
    amount = request.form.get("amount", type=float)
    returned_on = request.form.get("returned_on", "")

    if not name or amount is None:
        return redirect(f"/expenses/{expense_id}", code=303)

    date_obj = datetime.date.today()
    if returned_on.strip():
        try:
            date_obj = datetime.date.fromisoformat(returned_on)
        except ValueError:
            pass

    db.add(ReturnedItem(expense_id=expense_id, name=name, amount=amount, returned_on=date_obj))
    db.commit()
    return redirect(f"/expenses/{expense_id}", code=303)


@bp.route("/<int:expense_id>/returns/<int:return_id>/delete", methods=["POST"])
def delete_returned_item(expense_id, return_id):
    db = get_db()
    get_expense_or_404(expense_id, db)
    returned_item = (
        db.query(ReturnedItem)
        .filter(ReturnedItem.id == return_id, ReturnedItem.expense_id == expense_id)
        .first()
    )
    if returned_item:
        db.delete(returned_item)
        db.commit()
    return redirect(f"/expenses/{expense_id}", code=303)


# --------------------------------------------------------------------- report

@bp.route("/report")
def category_report():
    db = get_db()
    expenses = db.query(Expense).all()

    # Grouped by each item's own category, like the detail page shows, so a
    # receipt spanning multiple categories (see Expense.category_label)
    # contributes to each of them rather than being lumped under one. A
    # return is matched back to the item it came from by name so its
    # deduction lands in the right category; if there's no matching item
    # (or the expense was never itemized) it falls back to the expense's
    # single top-level category.
    totals = defaultdict(float)
    for expense in expenses:
        if not expense.items:
            if expense.net_amount:
                totals[expense.category or "Other"] += expense.net_amount
            continue

        item_category_by_name = {item.name: (item.category or "Other") for item in expense.items}
        for item in expense.items:
            totals[item.category or "Other"] += item.price or 0
        for returned in expense.returned_items:
            category = item_category_by_name.get(returned.name, expense.category or "Other")
            totals[category] -= returned.amount

    breakdown = sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    grand_total = sum(totals.values())

    # A category that shares its color with another (there are more
    # categories than hues, see CATEGORY_COLORS) would render as an
    # indistinguishable slice next to it, so those tail categories get
    # folded into "Other" here -- everything still appears in the table below.
    chart_items = breakdown[:7]
    other_total = sum(amount for _, amount in breakdown[7:])
    if other_total:
        chart_items = chart_items + [("Other", other_total)]

    radius = 70
    circumference = 2 * math.pi * radius
    cumulative = 0.0
    slices = []
    for label, amount in chart_items:
        fraction = (amount / grand_total) if grand_total else 0
        dash = fraction * circumference
        slices.append({
            "label": label,
            "amount": amount,
            "pct": fraction * 100,
            "color": CATEGORY_COLORS.get(label, "#94a3b8"),
            "dasharray": f"{dash:.2f} {circumference - dash:.2f}",
            "dashoffset": f"{-cumulative:.2f}",
        })
        cumulative += dash

    return render_template(
        "expenses/report.html",
        breakdown=breakdown,
        grand_total=grand_total,
        slices=slices,
        radius=radius,
        circumference=circumference,
    )
