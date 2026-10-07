"""Database engine, session factory, and initialization management."""

import logging
from collections.abc import Generator
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)


def get_engine_args(database_url: str) -> dict:
    """Return appropriate engine arguments depending on dialect."""
    args = {}
    if database_url.startswith("sqlite"):
        args["connect_args"] = {"check_same_thread": False}
    return args


# Current active engine and sessionmaker
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine for current settings."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            **get_engine_args(settings.DATABASE_URL),
        )
        _SessionLocal = sessionmaker(
            bind=_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _engine


def get_sessionmaker() -> sessionmaker:
    """Get the active sessionmaker."""
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def set_engine_and_sessionmaker(new_engine: Engine) -> None:
    """Allow overriding engine and sessionmaker (used for test isolation)."""
    global _engine, _SessionLocal
    _engine = new_engine
    _SessionLocal = sessionmaker(
        bind=new_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def reset_engine() -> None:
    """Reset engine and sessionmaker so they re-initialize from settings."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def SessionLocal() -> Session:
    """Create a new Session instance from the active sessionmaker."""
    sm = get_sessionmaker()
    return sm()


def init_db(db_engine: Optional[Engine] = None) -> None:
    """Initialize database tables and ensure directory existence for SQLite."""
    target_engine = db_engine if db_engine is not None else get_engine()
    if settings.DATABASE_URL.startswith("sqlite:///"):
        db_path_str = settings.DATABASE_URL.replace("sqlite:///", "")
        db_path = Path(db_path_str)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=target_engine)
    logger.info("Database tables initialized successfully.")


def get_db() -> Generator[Session, None, None]:
    """Dependency helper yielding a SQLAlchemy session."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
