"""Admin authentication: login, bootstrap status, current admin and password change."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models import SystemSetting

router = APIRouter(prefix="/api/auth", tags=["auth"])

ADMIN_AUTH_KEY = "admin_auth"


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


async def _get_admin_auth(session: AsyncSession) -> dict | None:
    """Stored admin credentials ({"username", "password_hash"}), or None when unset."""
    row = await session.get(SystemSetting, ADMIN_AUTH_KEY)
    return row.value if row is not None else None


def _verify_admin(username: str, password: str, stored: dict | None) -> bool:
    """Check credentials against the stored hash, falling back to env defaults."""
    settings = get_settings()
    if stored and stored.get("password_hash"):
        return username == str(stored.get("username") or "") and verify_password(
            password, str(stored["password_hash"])
        )
    return username == settings.admin_username and password == settings.admin_password


@router.post("/login")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Admin login; returns a JWT access token."""
    if not _verify_admin(payload.username, payload.password, await _get_admin_auth(session)):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    settings = get_settings()
    token = create_access_token(
        payload.username,
        secret_key=settings.secret_key,
        expires_minutes=settings.access_token_expire_minutes,
    )
    return {"access_token": token, "token_type": "bearer", "username": payload.username}


@router.get("/bootstrap")
async def bootstrap(session: AsyncSession = Depends(get_db)) -> dict:
    """Whether the admin still uses the initial default credentials."""
    settings = get_settings()
    default_credentials = (
        await session.get(SystemSetting, ADMIN_AUTH_KEY) is None
        and settings.admin_password == "admin123"
    )
    return {"default_credentials": default_credentials}


@router.get("/me")
async def me(current_admin: str = Depends(get_current_admin)) -> dict:
    return {"username": current_admin}


@router.put("/password")
async def change_password(
    payload: ChangePasswordRequest,
    session: AsyncSession = Depends(get_db),
    current_admin: str = Depends(get_current_admin),
) -> dict:
    """Change the admin password (persists a PBKDF2 hash in ``admin_auth``)."""
    stored = await _get_admin_auth(session)
    settings = get_settings()
    if stored and stored.get("password_hash"):
        old_ok = verify_password(payload.old_password, str(stored["password_hash"]))
    else:
        old_ok = payload.old_password == settings.admin_password
    if not old_ok:
        raise HTTPException(status_code=400, detail="原密码错误")

    value = {"username": current_admin, "password_hash": hash_password(payload.new_password)}
    row = await session.get(SystemSetting, ADMIN_AUTH_KEY)
    if row is None:
        session.add(SystemSetting(key=ADMIN_AUTH_KEY, value=value))
    else:
        row.value = value
    return {"ok": True}
