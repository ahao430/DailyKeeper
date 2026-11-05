"""Resource snapshots: filtered history and latest-value summary per account/type."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.models import Account, ResourceSnapshot

router = APIRouter(
    prefix="/api/resources", tags=["resources"], dependencies=[Depends(get_current_admin)]
)

# 汇总只扫描最近 2000 条快照（V1 实现说明，见 docs/API.md）
SUMMARY_SCAN_LIMIT = 2000


def _dt(value: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601; None stays None."""
    return value.isoformat() if value is not None else None


def _as_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _snapshot_detail(snapshot: ResourceSnapshot, account: Account) -> dict:
    """Serialize one snapshot (its account relationships must be loaded)."""
    return {
        "id": snapshot.id,
        "account_id": snapshot.account_id,
        "account_name": account.name,
        "resource_type": snapshot.resource_type,
        "value": _as_float(snapshot.value),
        "text_value": snapshot.text_value,
        "unit": snapshot.unit,
        "observed_at": _dt(snapshot.observed_at),
        "source": snapshot.source,
    }


@router.get("")
async def list_resources(
    account_id: int | None = Query(None),
    resource_type: str | None = Query(None),
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Resource snapshots, newest first, optionally filtered by account and type."""
    query = select(ResourceSnapshot, Account).join(
        Account, ResourceSnapshot.account_id == Account.id
    )
    if account_id is not None:
        query = query.where(ResourceSnapshot.account_id == account_id)
    if resource_type is not None:
        query = query.where(ResourceSnapshot.resource_type == resource_type)

    rows = (
        await session.execute(
            query.order_by(ResourceSnapshot.observed_at.desc(), ResourceSnapshot.id.desc()).limit(limit)
        )
    ).all()
    return [_snapshot_detail(snapshot, account) for snapshot, account in rows]


@router.get("/summary")
async def summarize_resources(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """Latest value per (account, resource_type), most recently observed first."""
    rows = (
        await session.execute(
            select(ResourceSnapshot, Account)
            .join(Account, ResourceSnapshot.account_id == Account.id)
            .order_by(ResourceSnapshot.observed_at.desc(), ResourceSnapshot.id.desc())
            .limit(SUMMARY_SCAN_LIMIT)
        )
    ).all()

    latest: dict[tuple[int, str], dict] = {}
    for snapshot, account in rows:
        key = (snapshot.account_id, snapshot.resource_type)
        if key in latest:
            continue
        latest[key] = {
            "account_id": snapshot.account_id,
            "account_name": account.name,
            "platform_id": account.instance.platform_id,
            "instance_name": account.instance.name,
            "resource_type": snapshot.resource_type,
            "value": _as_float(snapshot.value),
            "text_value": snapshot.text_value,
            "unit": snapshot.unit,
            "observed_at": _dt(snapshot.observed_at),
        }
    return list(latest.values())
