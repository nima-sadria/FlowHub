"""FlowHub - database session factory (BU2).

Reads FLOWHUB_DATABASE_URL from the environment.  Provides FlowHubBase (the
declarative base shared by all FlowHub ORM models) and a get_db() FastAPI
dependency that yields a SQLAlchemy Session.

Engine creation is cached per URL string so that the connection pool is
reused across requests.  Tests override get_db via dependency_overrides to
inject an in-memory SQLite session.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool


class FlowHubBase(DeclarativeBase):
    pass


@lru_cache(maxsize=4)
def _get_engine(db_url: str) -> Engine:
    """Return a cached SQLAlchemy engine for the given URL."""
    kwargs: dict[str, Any] = {}
    if db_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["poolclass"] = NullPool
    engine = create_engine(db_url, **kwargs)
    if db_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(
            dbapi_connection: Any, _connection_record: Any
        ) -> None:
            # sqlite3 ignores this PRAGMA inside a transaction.  Temporarily
            # use autocommit on Python versions that expose the attribute so
            # every pooled connection enforces the declared schema FKs.
            previous_autocommit = getattr(dbapi_connection, "autocommit", None)
            if previous_autocommit is not None:
                dbapi_connection.autocommit = True
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()
                if previous_autocommit is not None:
                    dbapi_connection.autocommit = previous_autocommit
    return engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a database session, close on exit."""
    url = os.environ.get("FLOWHUB_DATABASE_URL", "")
    if not url:
        raise RuntimeError("FLOWHUB_DATABASE_URL is not configured")
    engine = _get_engine(url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
