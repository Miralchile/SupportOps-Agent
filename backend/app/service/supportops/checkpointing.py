"""LangGraph checkpoint lifecycle for SupportOps.

PostgreSQL is used in deployed environments. Tests and local import-only tools can
fall back to an in-memory saver when no database is configured or reachable.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


logger = logging.getLogger(__name__)

_lock = threading.Lock()
_checkpointer: Any | None = None
_pool: ConnectionPool | None = None
_backend = "uninitialized"


def _close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


atexit.register(_close_pool)


def get_checkpointer() -> Any:
    global _checkpointer, _pool, _backend
    if _checkpointer is not None:
        return _checkpointer

    with _lock:
        if _checkpointer is not None:
            return _checkpointer

        database_url = (os.getenv("DATABASE_URL") or "").strip()
        if database_url.startswith(("postgresql://", "postgres://")):
            try:
                _pool = ConnectionPool(
                    conninfo=database_url,
                    min_size=1,
                    max_size=int(os.getenv("SUPPORTOPS_CHECKPOINT_POOL_SIZE", "8")),
                    open=True,
                    kwargs={
                        "autocommit": True,
                        "prepare_threshold": 0,
                        "row_factory": dict_row,
                    },
                )
                _pool.wait(timeout=15)
                saver = PostgresSaver(_pool)
                saver.setup()
                _checkpointer = saver
                _backend = "postgres"
                return _checkpointer
            except Exception:
                logger.exception("PostgreSQL checkpoint initialization failed; using memory fallback")
                _close_pool()

        _checkpointer = InMemorySaver()
        _backend = "memory"
        return _checkpointer


def checkpoint_status() -> dict[str, Any]:
    get_checkpointer()
    return {
        "backend": _backend,
        "durable": _backend == "postgres",
    }


def reset_checkpointer_for_tests() -> None:
    """Reset singleton state. Only intended for isolated tests."""
    global _checkpointer, _backend
    with _lock:
        _close_pool()
        _checkpointer = None
        _backend = "uninitialized"
