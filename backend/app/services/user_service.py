"""User management service: startup seeding of the initial admin account."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import SystemSetting, User

ADMIN_AUTH_KEY = "admin_auth"


async def ensure_admin_user(session: AsyncSession) -> None:
    """Seed the initial admin user when no users exist yet.

    Password hash source: the legacy ``admin_auth`` SystemSetting (migrating a
    previously changed password), falling back to the environment default
    ``admin_password``. Called by ``run_startup`` after ``create_all``.
    """
    count = await session.scalar(select(func.count()).select_from(User))
    if count:
        return

    settings = get_settings()
    legacy = await session.get(SystemSetting, ADMIN_AUTH_KEY)
    legacy_hash = (legacy.value or {}).get("password_hash") if legacy is not None else None
    password_hash = (
        str(legacy_hash) if legacy_hash else hash_password(settings.admin_password)
    )
    session.add(
        User(
            username=settings.admin_username,
            password_hash=password_hash,
            display_name="管理员",
        )
    )
    await session.commit()
