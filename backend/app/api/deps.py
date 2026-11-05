"""Shared FastAPI dependencies: per-request DB session and admin authentication."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.security import decode_token

_UNAUTHORIZED = "未登录或登录已过期"


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield one DB session per request, committing on success."""
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def get_current_admin(authorization: str = Header(default="")) -> str:
    """Resolve the admin username from the ``Authorization: Bearer`` header."""
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)
    payload = decode_token(
        authorization[len(prefix) :].strip(), secret_key=get_settings().secret_key
    )
    subject = (payload or {}).get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)
    return str(subject)
