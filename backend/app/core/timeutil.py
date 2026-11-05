"""Timezone helpers. All DB datetimes are naive UTC; per-site timezone only affects business_date and scheduling."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _resolve_tz(tz_name: str) -> tzinfo:
    """Resolve a tz name; fall back to UTC with a warning when invalid."""
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - 常见为 ZoneInfoNotFoundError，也可能是其他非法输入
        logger.warning("无效时区 %s，回退 UTC", tz_name)
        return timezone.utc


def now_utc() -> datetime:
    """Current time as a naive UTC datetime (matching the DB convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_in_tz(tz_name: str) -> datetime:
    """Current time in the given timezone, returned as a naive datetime."""
    return datetime.now(timezone.utc).astimezone(_resolve_tz(tz_name)).replace(tzinfo=None)


def date_in_tz(tz_name: str) -> date:
    """Current calendar date in the given timezone."""
    return datetime.now(timezone.utc).astimezone(_resolve_tz(tz_name)).date()


def parse_hhmm(s: str) -> time:
    """Parse an ``H:MM`` or ``HH:MM`` string into a ``time``.

    Raises ValueError on any other input.
    """
    match = _HHMM_RE.match((s or "").strip())
    if match is None:
        raise ValueError("无效时间格式，应为 HH:MM")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("无效时间格式，应为 HH:MM")
    return time(hour=hour, minute=minute)


def next_occurrence(
    hhmm: str, interval_days: int, tz_name: str, after: datetime | None = None
) -> datetime:
    """Next occurrence of ``hhmm`` (site-local time) as a naive UTC datetime.

    ``after`` is a naive UTC datetime; defaults to the current time. The
    returned datetime is the first ``hhmm`` site-local moment strictly after
    ``after``, stepping by ``interval_days`` when today's moment already
    passed.
    """
    t = parse_hhmm(hhmm)
    after_utc = after if after is not None else now_utc()
    if after_utc.tzinfo is None:
        after_utc = after_utc.replace(tzinfo=timezone.utc)
    now_local = after_utc.astimezone(_resolve_tz(tz_name))
    candidate = now_local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=interval_days)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def to_utc(local: datetime, tz_name: str) -> datetime:
    """Convert a (naive) local datetime in ``tz_name`` to naive UTC."""
    if local.tzinfo is None:
        local = local.replace(tzinfo=_resolve_tz(tz_name))
    return local.astimezone(timezone.utc).replace(tzinfo=None)
