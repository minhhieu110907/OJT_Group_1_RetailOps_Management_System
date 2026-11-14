"""SQLAlchemy engine, session factory, and FastAPI dependency."""

import os
from collections.abc import Generator
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _create_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args={"connect_timeout": 5},
    )


# Unit/API tests construct an app with injected settings and do not need a DB engine.
# Integration/runtime environments provide RETAILOPS_DB_HOST before this import.
engine: Engine | None = _create_engine() if os.getenv("RETAILOPS_DB_HOST") else None
SessionLocal = (
    sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    if engine is not None
    else None
)
_session_factory_lock = Lock()


def get_session_factory() -> sessionmaker[Session]:
    """Return the process session factory, creating its engine lazily."""
    global engine, SessionLocal
    if SessionLocal is None:
        with _session_factory_lock:
            if SessionLocal is None:
                engine = _create_engine()
                SessionLocal = sessionmaker(
                    bind=engine, autoflush=False, expire_on_commit=False
                )
    return SessionLocal


def get_db_session() -> Generator[Session]:
    """Yield one session and always roll back failed work before closing it."""
    with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


def commit_session(session: Session) -> None:
    """Explicitly commit the current transaction for endpoint coordinators."""
    session.commit()
