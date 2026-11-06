"""Account management: CRUD, AES-GCM encrypted credentials and inline credential check."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dailykeeper_sdk.registry import plugin_registry

from app.api.deps import get_current_admin, get_db
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.security import get_cipher
from app.core.timeutil import now_utc
from app.models import (
    Account,
    Credential,
    PlatformInstance,
    ResourceSnapshot,
    ScheduledTask,
    TaskExecution,
    TaskResultRecord,
)
from app.services.plugin_runtime import run_execution
from app.services.task_engine import create_execution

router = APIRouter(prefix="/api", tags=["accounts"], dependencies=[Depends(get_current_admin)])

# V1 认可的凭据类型；插件对其解释保持宽松
CREDENTIAL_KINDS = {"cookie", "token", "api_key", "username_password", "browser_session"}


class CredentialIn(BaseModel):
    kind: str
    data: dict


class CreateAccountRequest(BaseModel):
    instance_id: int
    name: str
    display_name: str = ""
    config: dict = {}
    credential: CredentialIn


class CredentialUpdate(BaseModel):
    kind: str | None = None
    data: dict | None = None


class UpdateAccountRequest(BaseModel):
    display_name: str | None = None
    config: dict | None = None
    enabled: bool | None = None
    notes: str | None = None
    credential: CredentialUpdate | None = None


def _dt(value: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601; None stays None."""
    return value.isoformat() if value is not None else None


def _account_detail(
    account: Account, instance: PlatformInstance, credential: Credential | None
) -> dict:
    """Serialize one account; credential secrets are never exposed, only metadata."""
    return {
        "id": account.id,
        "instance_id": account.instance_id,
        "instance_name": instance.name,
        "platform_id": instance.platform_id,
        "name": account.name,
        "display_name": account.display_name,
        "status": account.status,
        "enabled": account.enabled,
        "notes": account.notes,
        "config": account.config,
        "last_task_at": _dt(account.last_task_at),
        "last_checkin_date": (
            account.last_checkin_date.isoformat()
            if account.last_checkin_date is not None
            else None
        ),
        "has_credential": credential is not None,
        "credential_kind": credential.kind if credential is not None else None,
    }


async def _get_account_or_404(session: AsyncSession, account_id: int) -> Account:
    account = await session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .options(selectinload(Account.credential))
    )
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return account


@router.get("/accounts")
async def list_accounts(
    instance_id: int | None = Query(None), session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """All accounts, optionally filtered by platform instance."""
    query = select(Account).options(selectinload(Account.credential)).order_by(Account.id)
    if instance_id is not None:
        query = query.where(Account.instance_id == instance_id)
    accounts = (await session.scalars(query)).all()
    return [_account_detail(account, account.instance, account.credential) for account in accounts]


@router.post("/accounts")
async def create_account(payload: CreateAccountRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Create an account and store its credential encrypted (AES-GCM)."""
    instance = await session.get(PlatformInstance, payload.instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="平台实例不存在")

    plugin = plugin_registry.get(instance.platform_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"平台插件未加载: {instance.platform_id}")

    ok, message = plugin.validate_account_config(payload.config)
    if not ok:
        raise HTTPException(status_code=422, detail=message)

    kind = payload.credential.kind.strip()
    if not kind:
        raise HTTPException(status_code=422, detail="凭据类型不能为空")
    if kind not in CREDENTIAL_KINDS:
        raise HTTPException(status_code=422, detail=f"凭据类型无效: {kind}")

    account = Account(
        instance_id=instance.id,
        name=payload.name,
        display_name=payload.display_name,
        config=payload.config,
    )
    session.add(account)
    await session.flush()  # 取得 account.id 供凭据外键使用
    credential = Credential(
        account_id=account.id,
        kind=kind,
        data_encrypted=get_cipher(get_settings()).encrypt_dict(payload.credential.data),
    )
    session.add(credential)
    return _account_detail(account, instance, credential)


@router.get("/accounts/{account_id}")
async def get_account(account_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    account = await _get_account_or_404(session, account_id)
    return _account_detail(account, account.instance, account.credential)


@router.put("/accounts/{account_id}")
async def update_account(
    account_id: int, payload: UpdateAccountRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Partially update an account; supports replacing the encrypted credential."""
    account = await _get_account_or_404(session, account_id)

    if payload.config is not None:
        plugin = plugin_registry.get(account.instance.platform_id)
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"平台插件未加载: {account.instance.platform_id}")
        ok, message = plugin.validate_account_config(payload.config)
        if not ok:
            raise HTTPException(status_code=422, detail=message)

    updates = {
        field: value
        for field, value in payload.model_dump(exclude_unset=True).items()
        if field != "credential" and value is not None
    }
    for field, value in updates.items():
        setattr(account, field, value)

    credential = account.credential
    incoming = payload.credential
    if incoming is not None and incoming.data is not None:
        kind = incoming.kind or (credential.kind if credential is not None else None) or "cookie"
        encrypted = get_cipher(get_settings()).encrypt_dict(incoming.data)
        if credential is None:
            credential = Credential(account_id=account.id, kind=kind, data_encrypted=encrypted)
            session.add(credential)
        else:
            credential.kind = kind
            credential.data_encrypted = encrypted
    return _account_detail(account, account.instance, credential)


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    """Delete an account and all dependent rows (results, executions, snapshots, tasks, credential)."""
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    execution_ids = select(TaskExecution.id).where(TaskExecution.account_id == account_id)
    await session.execute(
        delete(TaskResultRecord).where(TaskResultRecord.execution_id.in_(execution_ids))
    )
    # 先删资源快照：快照同时按 account_id 与 execution_id 引用，
    # 若后删会在 SQLite 外键检查时阻塞 task_executions 的删除（500）
    await session.execute(delete(ResourceSnapshot).where(ResourceSnapshot.account_id == account_id))
    await session.execute(delete(TaskExecution).where(TaskExecution.account_id == account_id))
    await session.execute(delete(ScheduledTask).where(ScheduledTask.account_id == account_id))
    await session.execute(delete(Credential).where(Credential.account_id == account_id))
    await session.delete(account)
    return {"ok": True}


@router.post("/accounts/{account_id}/check")
async def check_account(account_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    """Inline credential check: runs the plugin's info/auth task and returns its result.

    执行在请求内完成（可能耗时接近 task_timeout），V1 可接受。
    """
    settings = get_settings()
    account = await _get_account_or_404(session, account_id)

    plugin = plugin_registry.get(account.instance.platform_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"平台插件未加载: {account.instance.platform_id}")

    declared = {task.name for task in plugin.task_definitions}
    if "get_user_info" in declared:
        task_name = "get_user_info"
    elif "auth_check" in declared:
        task_name = "auth_check"
    else:
        raise HTTPException(
            status_code=422, detail="该平台（插件）暂不支持凭据检测，可通过立即执行任务验证"
        )

    execution = await create_execution(session, account, task_name, due_at=now_utc(), force=True)
    if execution is None:  # pragma: no cover - force=True 不触发去重
        raise HTTPException(status_code=500, detail="执行创建失败")
    execution_id = execution.id

    # 置为 RUNNING 并先提交：run_execution 在独立会话中读取该状态
    await session.execute(
        update(TaskExecution)
        .where(TaskExecution.id == execution_id, TaskExecution.status == "PENDING")
        .values(status="RUNNING", worker_id="api", started_at=now_utc())
        .execution_options(synchronize_session=False)
    )
    await session.commit()

    await run_execution(
        execution_id,
        session_factory=get_session_factory(),
        cipher=get_cipher(settings),
        settings=settings,
    )

    record = await session.scalar(
        select(TaskResultRecord).where(TaskResultRecord.execution_id == execution_id)
    )
    if record is None:
        raise HTTPException(status_code=500, detail="执行未产生结果记录")
    return {
        "ok": record.success,
        "status": record.status,
        "message": record.message,
        "data": record.data,
        "metrics": record.metrics,
        "execution_id": execution_id,
    }
