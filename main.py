"""
HomeUtil -- entry point.

Run directly with:   python main.py
Or via a WSGI server: gunicorn main:app
"""
from flask import Flask

import models  # noqa: F401  (import registers ORM models before create_all)
from config import DEBUG, HOST, PORT
from database import Base, check_schema_is_current, close_db, engine
from models import CATEGORY_COLORS
from rendering import format_currency, format_number
from routes.chores import bp as chores_bp
from routes.dashboard import bp as dashboard_bp
from routes.expenses import bp as expenses_bp
from routes.vehicles import bp as vehicles_bp

# Create tables on startup if they don't exist yet. Safe to call every time.
Base.metadata.create_all(bind=engine)

# Fail fast with a clear message if a model column is missing from an
# existing table, rather than letting the first request that touches it 500.
check_schema_is_current()

app = Flask(__name__)

app.jinja_env.filters["number"] = format_number
app.jinja_env.filters["currency"] = format_currency
app.context_processor(lambda: {"category_colors": CATEGORY_COLORS})

app.teardown_appcontext(close_db)

app.register_blueprint(dashboard_bp)
app.register_blueprint(vehicles_bp)
app.register_blueprint(chores_bp)
app.register_blueprint(expenses_bp)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
