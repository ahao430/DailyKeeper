"""Admin authentication: login, bootstrap status, current admin and password change."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timeutil import now_utc
from app.models import SystemSetting, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

PASSWORD_CHANGED_KEY = "password_changed"


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


@router.post("/login")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Admin login; returns a JWT access token (subject = username)."""
    user = await session.scalar(select(User).where(User.username == payload.username))
    if (
        user is None
        or not verify_password(payload.password, user.password_hash)
        or not user.enabled
    ):
        # 禁用账号与口令错误返回同一提示，避免账号枚举
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    settings = get_settings()
    token = create_access_token(
        user.username,
        secret_key=settings.secret_key,
        expires_minutes=settings.access_token_expire_minutes,
    )
    user.last_login_at = now_utc()
    await session.commit()
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@router.get("/bootstrap")
async def bootstrap(session: AsyncSession = Depends(get_db)) -> dict:
    """Whether the setup still runs on the initial default credentials."""
    user_count = await session.scalar(select(func.count()).select_from(User))
    default_credentials = (
        user_count == 1 and await session.get(SystemSetting, PASSWORD_CHANGED_KEY) is None
    )
    return {"default_credentials": default_credentials}


@router.get("/me")
async def me(current_admin: User = Depends(get_current_admin)) -> dict:
    return {
        "username": current_admin.username,
        "display_name": current_admin.display_name,
        "role": current_admin.role,
    }


@router.put("/password")
async def change_password(
    payload: ChangePasswordRequest,
    session: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> dict:
    """Change the current user's password (persists a PBKDF2 hash on the user)."""
    if not verify_password(payload.old_password, current_admin.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")

    current_admin.password_hash = hash_password(payload.new_password)
    row = await session.get(SystemSetting, PASSWORD_CHANGED_KEY)
    if row is None:
        session.add(SystemSetting(key=PASSWORD_CHANGED_KEY, value={"changed": True}))
    else:
        row.value = {"changed": True}
    return {"ok": True}
