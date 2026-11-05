"""Async database engine and session factory for DailyKeeper.

Engine is initialized explicitly (``init_engine``) so that the API process,
scheduler and worker daemons — and tests — can control startup order.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _configure_sqlite_pragmas(engine: AsyncEngine) -> None:
    """Enable WAL / foreign keys / busy timeout for SQLite connections."""

    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


def init_engine(settings: Settings | None = None) -> None:
    """Create the global engine + session factory (idempotent)."""

    global _engine, _session_factory
    if _engine is not None:
        return
    settings = settings or get_settings()
    kwargs: dict = {"echo": False, "future": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 15}
    _engine = create_async_engine(settings.database_url, **kwargs)
    if settings.database_url.startswith("sqlite"):
        _configure_sqlite_pragmas(_engine)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info("数据库引擎已初始化: %s", settings.database_url.split("://")[0])


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("数据库未初始化：请先调用 init_engine(settings)")
    return _session_factory


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("数据库未初始化：请先调用 init_engine(settings)")
    return _engine


async def ensure_schema() -> None:
    """Create all tables if missing (idempotent).

    Daemons call this before touching data so they can start in parallel
    with the API process; versioned upgrades remain Alembic's job.
    """
    from app.models.tables import Base

    if _engine is None:
        raise RuntimeError("数据库未初始化：请先调用 init_engine(settings)")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose the engine (used on shutdown / between test sessions)."""

    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
