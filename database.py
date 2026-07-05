"""
Database engine and session setup.

This is the only file that should know about SQLAlchemy's engine
internals. Routes never talk to the engine directly -- they get a
session through get_db(), which keeps the rest of the app portable
if the underlying database ever changes.
"""
import sys

from flask import g
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import DATABASE_URL, BASE_DIR

# Make sure the data/ folder exists before SQLite tries to create the file in it.
(BASE_DIR / "data").mkdir(exist_ok=True)

# check_same_thread=False is only needed for SQLite, which by default
# forbids using a connection from a thread other than the one that
# created it. Flask's dev server (and most WSGI servers) may serve
# requests from a thread pool, so we relax that restriction. This
# option is ignored for other databases.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Calling SessionLocal() gives a new database session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class that all ORM models inherit from."""
    pass


def get_db():
    """
    Returns a database session scoped to the current request. The
    first call in a request opens the session; it is closed
    automatically by close_db() when the request ends, even on error.
    """
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


def close_db(exception=None):
    """Registered as a Flask teardown handler in main.py."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def check_schema_is_current():
    """This project has no migration framework (see CLAUDE.md) --
    Base.metadata.create_all() only creates missing tables, it never adds
    columns to existing ones. So a model change like adding a column needs
    a manual `ALTER TABLE`, and forgetting to run it against an existing db
    used to surface as a confusing 500 the first time a route touched that
    column. Catch that here instead, at startup, with a clear fix.

    Only compares tables that already exist -- a table created moments ago
    by create_all() is trivially in sync and not worth inspecting."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing_columns:
                missing.append((table.name, column.name, column.type))

    if not missing:
        return

    print("Database schema is out of date -- missing columns:", file=sys.stderr)
    for table_name, column_name, column_type in missing:
        print(
            f"  ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type};",
            file=sys.stderr,
        )
    print(
        "Run the statement(s) above against your database (see CLAUDE.md's "
        "'Schema changes require manual migration' section), then restart.",
        file=sys.stderr,
    )
    sys.exit(1)
