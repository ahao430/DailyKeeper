"""System information, general settings and notification channel management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dailykeeper_sdk.registry import plugin_registry

from app.api.deps import get_current_admin, get_db
from app.core.config import Settings, get_settings
from app.core.timeutil import date_in_tz, now_utc
from app.models import Account, PlatformInstance, ScheduledTask, SystemSetting, TaskExecution
from app.notifications import CHANNEL_TYPES
from app.services.notification_service import (
    NOTIFICATION_SETTINGS_KEY,
    get_notification_config,
    send_test,
)
from app.services.scheduler_service import SCHEDULER_HEARTBEAT_KEY

router = APIRouter(
    prefix="/api/system", tags=["system"], dependencies=[Depends(get_current_admin)]
)


def _parse_heartbeat_at(raw: object) -> datetime | None:
    """Parse the scheduler heartbeat timestamp into naive UTC; None when invalid."""
    if not raw:
        return None
    try:
        at = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if at.tzinfo is not None:
        at = at.astimezone(timezone.utc).replace(tzinfo=None)
    return at


def _heartbeat_info(value: dict | None, settings: Settings) -> dict | None:
    """Heartbeat freshness window is 3x the scheduler interval."""
    at = _parse_heartbeat_at((value or {}).get("at"))
    if at is None:
        return None
    fresh_window = timedelta(seconds=3 * settings.scheduler_interval_seconds)
    return {"at": at.isoformat(), "fresh": now_utc() - at < fresh_window}


@router.get("/info")
async def system_info(session: AsyncSession = Depends(get_db)) -> dict:
    """Server overview: versions, counts and the scheduler heartbeat."""
    settings = get_settings()
    today = date_in_tz(settings.timezone)

    instances = await session.scalar(select(func.count()).select_from(PlatformInstance))
    accounts = await session.scalar(select(func.count()).select_from(Account))
    scheduled_tasks = await session.scalar(select(func.count()).select_from(ScheduledTask))
    executions_today = await session.scalar(
        select(func.count()).select_from(TaskExecution).where(TaskExecution.business_date == today)
    )
    executions_today_success = await session.scalar(
        select(func.count())
        .select_from(TaskExecution)
        .where(TaskExecution.business_date == today, TaskExecution.status == "SUCCESS")
    )
    heartbeat_row = await session.get(SystemSetting, SCHEDULER_HEARTBEAT_KEY)
    notifications = await get_notification_config(session)

    return {
        "app_name": settings.app_name,
        "version": settings.version,
        "env": settings.env,
        "database": "sqlite",
        "timezone": settings.timezone,
        "plugins": len(plugin_registry.all()),
        "instances": instances,
        "accounts": accounts,
        "scheduled_tasks": scheduled_tasks,
        "executions_today": executions_today,
        "executions_today_success": executions_today_success,
        "notifications_enabled": notifications.get("enabled", True),
        "scheduler_heartbeat": _heartbeat_info(
            heartbeat_row.value if heartbeat_row is not None else None, settings
        ),
    }


@router.get("/settings")
async def read_settings(session: AsyncSession = Depends(get_db)) -> dict:
    """Notification config (merged over defaults) plus read-only general settings."""
    settings = get_settings()
    return {
        "notifications": await get_notification_config(session),
        "general": {
            "timezone": settings.timezone,
            "env": settings.env,
            "version": settings.version,
        },
    }


@router.put("/settings/notifications")
async def update_notification_settings(
    payload: dict, session: AsyncSession = Depends(get_db)
) -> dict:
    """Replace the stored notification config; channel entries are validated on write."""
    channels = payload.get("channels") or []
    if not isinstance(channels, list) or not all(isinstance(item, dict) for item in channels):
        raise HTTPException(status_code=422, detail="通知渠道配置必须是列表")
    for channel in channels:
        channel_type = str(channel.get("type") or "")
        if channel_type not in CHANNEL_TYPES:
            raise HTTPException(status_code=422, detail=f"未知通知渠道类型: {channel_type}")
        if not str(channel.get("name") or "").strip():
            raise HTTPException(status_code=422, detail="通知渠道名称不能为空")

    row = await session.get(SystemSetting, NOTIFICATION_SETTINGS_KEY)
    if row is None:
        session.add(SystemSetting(key=NOTIFICATION_SETTINGS_KEY, value=payload))
    else:
        row.value = payload
    return {"ok": True}


@router.post("/notifications/test")
async def test_notification(payload: dict, session: AsyncSession = Depends(get_db)) -> dict:
    """Send a test notification through one channel spec ({type, name, config})."""
    ok, error = await send_test(session, payload)
    return {"ok": ok, "error": error}
