"""
Database engine and session setup.

This is the only file that should know about SQLAlchemy's engine
internals. Routes never talk to the engine directly -- they get a
session through get_db(), which keeps the rest of the app portable
if the underlying database ever changes.
"""
from flask import g
from sqlalchemy import create_engine
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
