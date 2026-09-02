"""
HomeUtil -- entry point.

Run directly with:   python main.py
Or via a WSGI server: gunicorn main:app
"""
from flask import Flask

import models  # noqa: F401  (import registers ORM models before create_all)
from config import DEBUG, HOST, PORT
from database import Base, SessionLocal, check_schema_is_current, close_db, engine
from models import CATEGORY_COLORS, DEFAULT_VENDOR_DOMAIN_OVERRIDES, VendorDomainOverride
from rendering import format_currency, format_number
from routes.chores import bp as chores_bp
from routes.dashboard import bp as dashboard_bp
from routes.expenses import bp as expenses_bp
from routes.filter_maintenance import bp as filter_maintenance_bp
from routes.kids_classes import bp as kids_classes_bp
from routes.vehicles import bp as vehicles_bp

# Create tables on startup if they don't exist yet. Safe to call every time.
Base.metadata.create_all(bind=engine)

# Fail fast with a clear message if a model column is missing from an
# existing table, rather than letting the first request that touches it 500.
check_schema_is_current()

# Seed known vendor-domain corrections once, so they work out of the box --
# but only if the table is empty, so this never overwrites edits made later
# on the Vendor Domains settings page.
with SessionLocal() as _db:
    if _db.query(VendorDomainOverride).count() == 0:
        for _match_text, _domain in DEFAULT_VENDOR_DOMAIN_OVERRIDES:
            _db.add(VendorDomainOverride(match_text=_match_text, domain=_domain))
        _db.commit()

app = Flask(__name__)

app.jinja_env.filters["number"] = format_number
app.jinja_env.filters["currency"] = format_currency
app.context_processor(lambda: {"category_colors": CATEGORY_COLORS})

app.teardown_appcontext(close_db)

app.register_blueprint(dashboard_bp)
app.register_blueprint(vehicles_bp)
app.register_blueprint(chores_bp)
app.register_blueprint(expenses_bp)
app.register_blueprint(kids_classes_bp)
app.register_blueprint(filter_maintenance_bp)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
