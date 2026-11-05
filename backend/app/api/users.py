"""用户管理：多管理员账号的增删改查与密码重置（管理端，需管理员登录）。

停用或删除用户后，其已有 JWT 因令牌解析走 ``users`` 表而立即失效。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.core.security import hash_password
from app.models import User

router = APIRouter(
    prefix="/api/users", tags=["users"], dependencies=[Depends(get_current_admin)]
)


class CreateUserRequest(BaseModel):
    username: str
    password: str = Field(min_length=6)
    display_name: str = ""


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6)


def _dt(value: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601; None stays None."""
    return value.isoformat() if value is not None else None


def _user_detail(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "enabled": user.enabled,
        "last_login_at": _dt(user.last_login_at),
        "created_at": _dt(user.created_at),
    }


async def _get_user_or_404(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.get("")
async def list_users(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """所有用户（按创建顺序），不含口令哈希。"""
    users = (await session.scalars(select(User).order_by(User.id))).all()
    return [_user_detail(user) for user in users]


@router.post("")
async def create_user(payload: CreateUserRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """创建一个管理员账号；用户名唯一。"""
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="用户名不能为空")

    duplicate = await session.scalar(select(User.id).where(User.username == username).limit(1))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role="admin",
    )
    session.add(user)
    await session.commit()
    return _user_detail(user)


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    session: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> dict:
    """修改用户的显示名或启用状态；不能停用自己的账号。"""
    user = await _get_user_or_404(session, user_id)
    if payload.enabled is False and user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="不能停用自己的账号")
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.enabled is not None:
        user.enabled = payload.enabled
    await session.commit()
    return _user_detail(user)


@router.put("/{user_id}/password")
async def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """管理员重置某用户的密码（用户下次登录使用新密码）。"""
    user = await _get_user_or_404(session, user_id)
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return {"ok": True}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> dict:
    """删除用户；不能删除自己，且至少保留一个用户。"""
    user = await _get_user_or_404(session, user_id)
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    total = await session.scalar(select(func.count()).select_from(User))
    if total is not None and total <= 1:
        raise HTTPException(status_code=400, detail="至少保留一个用户")
    await session.delete(user)
    await session.commit()
    return {"ok": True}
