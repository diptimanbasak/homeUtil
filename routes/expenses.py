"""Expenses module: track spending by scanning receipt photos."""
import datetime
import itertools
import math
import uuid
from collections import defaultdict

import pytesseract
from flask import Blueprint, abort, redirect, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from config import RECEIPTS_DIR
from database import get_db
from models import (
    CATEGORY_COLORS,
    EXPENSE_CATEGORIES,
    Expense,
    ExpenseItem,
    ReturnedItem,
    VendorDomainOverride,
    categorize_by_vendor,
    guess_vendor_domain,
)
from receipts import convert_heic_to_jpeg, extract_receipt_data

bp = Blueprint("expenses", __name__, url_prefix="/expenses")

RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


def get_expense_or_404(expense_id: int, db) -> Expense:
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        abort(404, description="Expense not found")
    return expense


def _apply_filters(query, args):
    """Shared date/category/vendor filtering for the list and report pages,
    both driven by the same GET query params so a link from one to the
    other (with filters intact) is a plain query-string carryover."""
    date_from = args.get("date_from", "")
    date_to = args.get("date_to", "")
    category = args.get("category", "")
    vendor = args.get("vendor", "").strip()
    item = args.get("item", "").strip()

    if date_from:
        try:
            query = query.filter(Expense.expense_date >= datetime.date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Expense.expense_date <= datetime.date.fromisoformat(date_to))
        except ValueError:
            pass
    if category in EXPENSE_CATEGORIES:
        # Mirrors Expense.category_label: an itemized expense is filtered by
        # its items' categories (since that's what the badge displays), not
        # by the single top-level category picked at scan time. Only an
        # expense with no items at all (e.g. manual entry) falls back to it.
        query = query.filter(
            Expense.items.any(ExpenseItem.category == category)
            | (~Expense.items.any() & (Expense.category == category))
        )
    if vendor:
        query = query.filter(Expense.vendor.ilike(f"%{vendor}%"))
    if item:
        query = query.filter(Expense.items.any(ExpenseItem.name.ilike(f"%{item}%")))

    return query


def _month_group(expense: Expense) -> str:
    if not expense.expense_date:
        return "No Date"
    return expense.expense_date.strftime("%B %Y")


# ------------------------------------------------------------------ list

@bp.route("/")
def list_expenses():
    db = get_db()
    query = _apply_filters(db.query(Expense), request.args)
    expenses = query.order_by(Expense.expense_date.desc().nullslast()).all()
    total = sum(e.amount for e in expenses if e.amount)

    months = [(label, list(group)) for label, group in itertools.groupby(expenses, key=_month_group)]

    return render_template(
        "expenses/list.html",
        expenses=expenses,
        months=months,
        total=total,
        categories=EXPENSE_CATEGORIES,
        filters=request.args,
    )


# ------------------------------------------------------------------ upload + analyze

def _last_uploaded_expense(db):
    return db.query(Expense).order_by(Expense.created_at.desc()).first()


@bp.route("/new", methods=["GET"])
def add_expense_form():
    db = get_db()
    return render_template("expenses/add_expense.html", error=None, last_expense=_last_uploaded_expense(db))


@bp.route("/new", methods=["POST"])
def create_expense():
    db = get_db()
    photo = request.files.get("receipt")

    if not photo or not photo.filename:
        return render_template(
            "expenses/add_expense.html", error="Please choose a receipt photo.", last_expense=_last_uploaded_expense(db)
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
        vendor_domain=guess_vendor_domain(extracted["vendor"], db=db),
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


# --------------------------------------------------------- manual entry

@bp.route("/new/manual", methods=["GET"])
def add_expense_manual_form():
    return render_template("expenses/add_expense_manual.html", categories=EXPENSE_CATEGORIES, error=None)


@bp.route("/new/manual", methods=["POST"])
def create_expense_manual():
    db = get_db()
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
                "expenses/add_expense_manual.html",
                categories=EXPENSE_CATEGORIES,
                error="Invalid date format.",
            ), 400

    expense = Expense(
        vendor=vendor.strip() or None,
        vendor_domain=guess_vendor_domain(vendor.strip() or None, db=db),
        amount=amount,
        expense_date=date_obj,
        category=category if category in EXPENSE_CATEGORIES else "Other",
        notes=notes.strip() or None,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
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
    vendor_domain = request.form.get("vendor_domain", "")
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
    expense.vendor_domain = vendor_domain.strip() or None
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

def _category_totals(expenses):
    """Grouped by each item's own category, like the detail page shows, so a
    receipt spanning multiple categories (see Expense.category_label)
    contributes to each of them rather than being lumped under one. A
    return is matched back to the item it came from by name so its
    deduction lands in the right category; if there's no matching item
    (or the expense was never itemized) it falls back to the expense's
    single top-level category."""
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

    return totals


def _month_key(expense: Expense):
    """Sortable (year, month) key, grouping undated expenses last."""
    if not expense.expense_date:
        return (9999, 99)
    return (expense.expense_date.year, expense.expense_date.month)


def _monthly_totals(expenses):
    """Net amount per calendar month (label via _month_group), in
    chronological order -- shared by the line, date-wise, and matrix views."""
    totals = defaultdict(float)
    for expense in expenses:
        if expense.net_amount:
            totals[_month_group(expense)] += expense.net_amount

    ordered_labels = sorted(
        totals.keys(),
        key=lambda label: min(_month_key(e) for e in expenses if _month_group(e) == label),
    )
    return [(label, totals[label]) for label in ordered_labels]


def _pie_chart_data(totals):
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

    return breakdown, grand_total, slices, radius, circumference


def _line_chart_points(monthly_totals, width=600, height=220, pad=30):
    """SVG polyline points for a simple month-over-month spend line, scaled
    to fit width x height with `pad` margin on every side -- no charting
    library, consistent with the pie chart's hand-rolled SVG."""
    if not monthly_totals:
        return [], []

    amounts = [amount for _, amount in monthly_totals]
    max_amount = max(amounts) or 1
    n = len(monthly_totals)
    plot_w = width - 2 * pad
    plot_h = height - 2 * pad

    points = []
    for i, (label, amount) in enumerate(monthly_totals):
        x = pad + (i * plot_w / (n - 1) if n > 1 else plot_w / 2)
        y = pad + plot_h - (amount / max_amount * plot_h)
        points.append({"x": round(x, 1), "y": round(y, 1), "label": label, "amount": amount})

    return points, [f"{p['x']},{p['y']}" for p in points]


def _category_comparison(date_wise):
    """Categorywise cost comparison between the two most recent month
    buckets in `date_wise` (chronological, same buckets as the Date-wise/
    Matrix views) -- e.g. this month vs last month, so the user can see at
    a glance which categories went up or down and by how much."""
    if len(date_wise) < 2:
        return None

    (prev_label, prev_expenses), (curr_label, curr_expenses) = date_wise[-2:]
    prev_totals = _category_totals(prev_expenses)
    curr_totals = _category_totals(curr_expenses)

    categories = [c for c in EXPENSE_CATEGORIES if prev_totals.get(c) or curr_totals.get(c)]
    rows = []
    for cat in categories:
        prev_amount = prev_totals.get(cat, 0.0)
        curr_amount = curr_totals.get(cat, 0.0)
        change = curr_amount - prev_amount
        if prev_amount:
            pct_change = change / prev_amount * 100
        else:
            pct_change = 100.0 if curr_amount else 0.0
        rows.append({
            "category": cat,
            "prev_amount": prev_amount,
            "curr_amount": curr_amount,
            "change": change,
            "pct_change": pct_change,
        })

    # Biggest increases first, so cost blowups surface at the top.
    rows.sort(key=lambda r: r["change"], reverse=True)

    return {
        "prev_label": prev_label,
        "curr_label": curr_label,
        "rows": rows,
        "prev_total": sum(prev_totals.values()),
        "curr_total": sum(curr_totals.values()),
    }


VALID_REPORT_VIEWS = ["pie", "line", "date", "category", "matrix", "comparison"]


@bp.route("/report")
def category_report():
    db = get_db()
    expenses = _apply_filters(db.query(Expense), request.args).all()

    view = request.args.get("view", "pie")
    if view not in VALID_REPORT_VIEWS:
        view = "pie"

    totals = _category_totals(expenses)
    breakdown, grand_total, slices, radius, circumference = _pie_chart_data(totals)

    monthly_totals = _monthly_totals(expenses)
    line_points, line_polyline = _line_chart_points(monthly_totals)

    # Date-wise: same month buckets as the expenses list, but sorted
    # chronologically here (the list page shows newest-first) since a
    # report reads more naturally as a timeline.
    date_wise = [
        (label, list(group))
        for label, group in itertools.groupby(
            sorted(expenses, key=_month_key), key=_month_group
        )
    ]

    # Monthly x category matrix: rows are months (chronological), columns
    # are every category that has at least one nonzero total anywhere, so
    # the table doesn't show columns of all-zero categories.
    matrix_rows = []
    matrix_categories = set()
    for label, month_expenses in date_wise:
        month_totals = _category_totals(month_expenses)
        matrix_categories.update(cat for cat, amount in month_totals.items() if amount)
        matrix_rows.append((label, month_totals, sum(month_totals.values())))
    matrix_categories = [c for c in EXPENSE_CATEGORIES if c in matrix_categories]
    matrix_column_totals = {
        cat: sum(month_totals.get(cat, 0) for _, month_totals, _ in matrix_rows)
        for cat in matrix_categories
    }

    comparison = _category_comparison(date_wise)

    return render_template(
        "expenses/report.html",
        view=view,
        breakdown=breakdown,
        grand_total=grand_total,
        slices=slices,
        radius=radius,
        circumference=circumference,
        monthly_totals=monthly_totals,
        line_points=line_points,
        line_polyline=" ".join(line_polyline),
        date_wise=date_wise,
        matrix_rows=matrix_rows,
        matrix_categories=matrix_categories,
        matrix_column_totals=matrix_column_totals,
        comparison=comparison,
        categories=EXPENSE_CATEGORIES,
        filters=request.args,
        filter_args={k: v for k, v in request.args.items() if k != "view"},
    )


# ------------------------------------------------------- vendor domains

def _clear_stale_vendor_domain(db, match_text: str):
    """An Expense's own vendor_domain (once set) always wins over the
    overrides table in Expense.logo_url, so adding/editing an override alone
    wouldn't change anything for expenses that already stored a (possibly
    wrong) guess before this override existed. Clearing it here makes the
    override actually take effect immediately for those expenses, instead
    of requiring a manual per-expense fix on the edit page."""
    db.query(Expense).filter(Expense.vendor.ilike(f"%{match_text}%")).update(
        {"vendor_domain": None}, synchronize_session=False
    )


@bp.route("/vendor-domains")
def list_vendor_domains():
    db = get_db()
    overrides = db.query(VendorDomainOverride).order_by(VendorDomainOverride.match_text).all()
    return render_template("expenses/vendor_domains.html", overrides=overrides, error=None)


@bp.route("/vendor-domains/new", methods=["POST"])
def create_vendor_domain():
    db = get_db()
    match_text = request.form.get("match_text", "").strip()
    domain = request.form.get("domain", "").strip()

    if not match_text or not domain:
        overrides = db.query(VendorDomainOverride).order_by(VendorDomainOverride.match_text).all()
        return render_template(
            "expenses/vendor_domains.html",
            overrides=overrides,
            error="Both Vendor Match and Domain are required.",
        ), 400

    db.add(VendorDomainOverride(match_text=match_text.lower(), domain=domain))
    _clear_stale_vendor_domain(db, match_text)
    db.commit()
    return redirect("/expenses/vendor-domains", code=303)


@bp.route("/vendor-domains/<int:override_id>/edit", methods=["POST"])
def update_vendor_domain(override_id):
    db = get_db()
    override = db.query(VendorDomainOverride).filter(VendorDomainOverride.id == override_id).first()
    if not override:
        abort(404, description="Override not found")

    match_text = request.form.get("match_text", "").strip()
    domain = request.form.get("domain", "").strip()

    if not match_text or not domain:
        overrides = db.query(VendorDomainOverride).order_by(VendorDomainOverride.match_text).all()
        return render_template(
            "expenses/vendor_domains.html",
            overrides=overrides,
            error="Both Vendor Match and Domain are required.",
        ), 400

    override.match_text = match_text.lower()
    override.domain = domain
    _clear_stale_vendor_domain(db, match_text)
    db.commit()
    return redirect("/expenses/vendor-domains", code=303)


@bp.route("/vendor-domains/<int:override_id>/delete", methods=["POST"])
def delete_vendor_domain(override_id):
    db = get_db()
    override = db.query(VendorDomainOverride).filter(VendorDomainOverride.id == override_id).first()
    if not override:
        abort(404, description="Override not found")
    db.delete(override)
    db.commit()
    return redirect("/expenses/vendor-domains", code=303)
