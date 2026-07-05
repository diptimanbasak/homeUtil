"""
Custom Jinja2 filters so templates can stay readable (no inline
Python format-string gymnastics). Registered on the Flask app in
main.py.
"""


def format_number(value):
    """1500 -> '1,500'. Used for mileage."""
    if value is None:
        return "—"
    return f"{int(value):,}"


def format_currency(value):
    """25.5 -> '$25.50'. Used for service cost."""
    if value is None:
        return "—"
    return f"${float(value):.2f}"
