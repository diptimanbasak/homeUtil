"""
Central configuration for HomeUtil.

Everything that might change between environments (local laptop,
Ubuntu home server, or eventually a cloud host) is read from an
environment variable with a sane local default. To move this app
to the cloud later, you would only need to set these env vars
differently -- no code changes required.
"""
import os
from pathlib import Path

# Root directory of the project (folder this file lives in)
BASE_DIR = Path(__file__).resolve().parent

# --- Database ---
# SQLite is a single file on disk -- perfect for a home server.
# To move to the cloud later, set DATABASE_URL to a Postgres/MySQL URL,
# e.g. "postgresql://user:password@host:5432/homeutil" -- the rest of
# the app (models, routes) does not need to change because SQLAlchemy
# abstracts the database engine.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'homeutil.db'}")

# --- Server ---
# 0.0.0.0 lets the app accept connections from other devices on your
# home network (phone, other PCs). Keep 127.0.0.1 for laptop-only use.
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# --- Maintenance reminder thresholds ---
# A reminder is "due soon" if its due date is within this many days,
# or its due mileage is within this many miles of the current odometer.
REMINDER_DUE_SOON_DAYS = int(os.getenv("REMINDER_DUE_SOON_DAYS", "30"))
REMINDER_DUE_SOON_MILES = int(os.getenv("REMINDER_DUE_SOON_MILES", "500"))

# --- Receipts ---
# Used to analyze uploaded receipt photos. Without it, receipts are
# still saved but vendor/amount/date/category must be entered manually.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
RECEIPTS_DIR = BASE_DIR / "data" / "receipts"
