"""Database engine / session management.

The engine is created lazily so that importing modules (tests, offline
scripts) does not require a configured database.
"""

import logging
import os
import threading

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base

load_dotenv()

logger = logging.getLogger("supportops.database")

_lock = threading.Lock()
_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                database_url = os.getenv("DATABASE_URL")
                if not database_url:
                    raise RuntimeError("DATABASE_URL 未配置，请在 .env 中设置数据库连接")
                _engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=3600)
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_factory


def SessionLocal(**kwargs):
    """Create a new SQLAlchemy session (factory-compatible callable)."""
    return _get_session_factory()(**kwargs)


def get_db():
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables that do not exist yet (idempotent)."""
    import models  # noqa: F401  (registers every model on Base.metadata)

    Base.metadata.create_all(bind=get_engine())
    logger.info("Database tables ensured")
