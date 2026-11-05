"""Notification service: config storage, event dispatch and test sends.

Imports only models/config/notifications (never the task engine) so that the
task engine can safely depend on this module.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationRecord, SystemSetting
from app.notifications import CHANNEL_TYPES

logger = logging.getLogger(__name__)

NOTIFICATION_SETTINGS_KEY = "notifications"

# 事件开关默认值遵循 plan.md §八：每日签到成功默认不通知，其余事件默认通知
DEFAULT_NOTIFICATION_CONFIG = {
    "enabled": True,
    "channels": [],
    "events": {
        "task_success": {"enabled": False},
        "task_failed": {"enabled": True},
        "auth_expired": {"enabled": True},
        "needs_action": {"enabled": True},
        "rate_limited": {"enabled": True},
        "resource_low": {"enabled": True},
        "agent_offline": {"enabled": True},
    },
    "thresholds": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into ``base``; override wins."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


async def get_notification_config(session: AsyncSession) -> dict:
    """Notification config stored under SystemSetting key ``notifications``,
    deep-merged over :data:`DEFAULT_NOTIFICATION_CONFIG`."""
    row = await session.get(SystemSetting, NOTIFICATION_SETTINGS_KEY)
    stored = (row.value if row is not None else None) or {}
    return _deep_merge(DEFAULT_NOTIFICATION_CONFIG, stored)


async def _send_via_channel(spec: dict, title: str, body: str) -> dict:
    """Send through one configured channel; return a result dict for the record."""
    channel_type = str(spec.get("type") or "")
    name = str(spec.get("name") or "")
    channel_class = CHANNEL_TYPES.get(channel_type)
    if channel_class is None:
        return {"type": channel_type, "name": name, "ok": False, "error": "未知渠道类型"}
    try:
        channel = channel_class(spec.get("config") or {})
        await channel.send(title, body)
    except Exception as exc:  # noqa: BLE001 - 单渠道失败不影响其他渠道
        logger.warning("通知渠道发送失败 type=%s name=%s: %s", channel_type, name, exc)
        return {"type": channel_type, "name": name, "ok": False, "error": str(exc)}
    return {"type": channel_type, "name": name, "ok": True, "error": ""}


async def notify(
    session: AsyncSession,
    event: str,
    title: str,
    body: str,
    context: dict | None = None,
) -> NotificationRecord:
    """Dispatch one notification event and persist a NotificationRecord.

    Does not commit; the caller owns the transaction (the task engine commits
    after finalize, the API layer after its own unit of work).
    """
    config = await get_notification_config(session)
    event_config = (config.get("events") or {}).get(event) or {}

    if not config.get("enabled", True) or not event_config.get("enabled", True):
        record = NotificationRecord(
            event=event, title=title, body=body, channels=[], status="SKIPPED"
        )
        session.add(record)
        await session.flush()
        return record

    specs = [
        spec
        for spec in (config.get("channels") or [])
        if isinstance(spec, dict) and spec.get("enabled", True)
    ]
    if specs:
        channel_results = list(
            await asyncio.gather(*(_send_via_channel(spec, title, body) for spec in specs))
        )
    else:
        channel_results = []

    if any(result.get("ok") for result in channel_results):
        status = "SENT"
    elif channel_results:
        status = "FAILED"
    else:
        status = "SKIPPED"

    record = NotificationRecord(
        event=event, title=title, body=body, channels=channel_results, status=status
    )
    session.add(record)
    await session.flush()
    logger.info("通知已处理 event=%s status=%s channels=%s", event, status, len(channel_results))
    return record


async def send_test(session: AsyncSession, spec: dict) -> tuple[bool, str]:
    """Send a test notification through one channel spec ({type, name, config}).

    Returns ``(ok, error)``; persists a NotificationRecord with event ``test``.
    The caller commits.
    """
    channel_type = str(spec.get("type") or "")
    name = str(spec.get("name") or "")
    channel_class = CHANNEL_TYPES.get(channel_type)
    if channel_class is None:
        ok, error = False, "未知渠道类型"
    else:
        try:
            channel = channel_class(spec.get("config") or {})
            await channel.send(
                "DailyKeeper 测试通知",
                "这是一条 DailyKeeper 测试通知，收到即表示该渠道配置正确。",
            )
            ok, error = True, ""
        except Exception as exc:  # noqa: BLE001 - 测试发送需把错误返回给调用方
            ok, error = False, str(exc)

    record = NotificationRecord(
        event="test",
        title="DailyKeeper 测试通知",
        body="这是一条 DailyKeeper 测试通知，收到即表示该渠道配置正确。",
        channels=[{"type": channel_type, "name": name, "ok": ok, "error": error}],
        status="SENT" if ok else "FAILED",
    )
    session.add(record)
    await session.flush()
    return ok, error
