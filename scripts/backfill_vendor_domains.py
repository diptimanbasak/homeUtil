"""
One-off backfill: fill Expense.vendor_domain for existing rows using the
same guess_vendor_domain() heuristic applied to new expenses, so old
expenses get a persisted guess instead of recomputing it on every page
load. Safe to re-run -- only touches rows where vendor_domain is still
NULL, and does nothing to rows already set (e.g. manually corrected).

Run from the project root after the vendor_domain column migration:
    source .venv/bin/activate
    python scripts/backfill_vendor_domains.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models import Expense, guess_vendor_domain


def main():
    db = SessionLocal()
    try:
        expenses = db.query(Expense).filter(Expense.vendor_domain.is_(None)).all()
        updated = 0
        for expense in expenses:
            domain = guess_vendor_domain(expense.vendor)
            if domain:
                expense.vendor_domain = domain
                updated += 1
                print(f"  #{expense.id} {expense.vendor!r} -> {domain}")
        db.commit()
        print(f"Updated {updated} of {len(expenses)} expense(s) missing a vendor_domain.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
