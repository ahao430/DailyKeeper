"""Agent 专用 API：令牌认证的心跳、任务认领、上下文获取与结果上报。

这些路由不走管理员 JWT，凭 ``X-Agent-Token`` 请求头认证（服务端仅保存
令牌的 SHA-256 摘要，无法反查明文）。
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dailykeeper_sdk import TaskResult, TaskStatus

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import get_cipher
from app.core.timeutil import now_utc
from app.models import Account, Agent, Credential, PlatformInstance, TaskExecution
from app.services.task_engine import claim_agent_tasks, finalize_execution

router = APIRouter(prefix="/api/agent", tags=["agent"])

# 心跳间隔（秒）：Agent 按该频率上报，服务端按 3 倍窗口判定离线
HEARTBEAT_INTERVAL_SECONDS = 30

_INVALID_TOKEN = "Agent 令牌无效"


async def get_current_agent(
    x_agent_token: str = Header(default=""),
    session: AsyncSession = Depends(get_db),
) -> Agent:
    """通过 ``X-Agent-Token`` 解析当前 Agent；令牌无效返回 401。"""
    if not x_agent_token:
        raise HTTPException(status_code=401, detail=_INVALID_TOKEN)
    token_hash = hashlib.sha256(x_agent_token.encode()).hexdigest()
    agent = await session.scalar(select(Agent).where(Agent.token_hash == token_hash))
    if agent is None:
        raise HTTPException(status_code=401, detail=_INVALID_TOKEN)
    return agent


class HeartbeatRequest(BaseModel):
    version: str = ""
    capabilities: list = []


class ClaimRequest(BaseModel):
    limit: int = Field(default=2, ge=1, le=5)


class AgentResultRequest(BaseModel):
    success: bool
    status: str
    message: str = ""
    data: dict = {}
    metrics: dict = {}


async def _get_owned_execution(
    session: AsyncSession, agent: Agent, execution_id: int
) -> TaskExecution:
    """加载执行记录并校验归属：不存在 404，未分配给当前 Agent 403。"""
    execution = await session.get(TaskExecution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if execution.assigned_agent_id != agent.id:
        raise HTTPException(status_code=403, detail="该任务未分配给当前 Agent")
    return execution


@router.post("/heartbeat")
async def heartbeat(
    payload: HeartbeatRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Agent 心跳：刷新在线状态、版本与能力列表。"""
    now = now_utc()
    agent.status = "ONLINE"
    agent.last_heartbeat = now
    agent.version = payload.version
    agent.meta = {**(agent.meta or {}), "capabilities": payload.capabilities}
    await session.commit()
    return {
        "ok": True,
        "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        "server_time": now.isoformat(),
    }


@router.post("/tasks/claim")
async def claim_tasks(
    payload: ClaimRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """认领到期的 Agent 执行线任务（PENDING → RUNNING，原子条件更新）。"""
    claimed = await claim_agent_tasks(session, agent, payload.limit)
    await session.commit()
    if not claimed:
        return []

    settings = get_settings()
    rows = (
        await session.execute(
            select(TaskExecution, PlatformInstance)
            .join(Account, TaskExecution.account_id == Account.id)
            .join(PlatformInstance, Account.instance_id == PlatformInstance.id)
            .where(TaskExecution.id.in_([execution.id for execution in claimed]))
            .order_by(TaskExecution.id)
        )
    ).all()
    return [
        {
            "id": execution.id,
            "task_name": execution.task_name,
            "platform_id": instance.platform_id,
            "params": execution.params,
            "timeout_seconds": settings.task_timeout_seconds,
        }
        for execution, instance in rows
    ]


@router.get("/tasks/{execution_id}/context")
async def task_context(
    execution_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """下发执行上下文：合并后的配置、base_url 与解密后的凭据。

    凭据明文仅在此接口出现，传输层安全（HTTPS/反向代理 TLS）必须在部署
    层保证；服务端日志不记录该响应。
    """
    execution = await _get_owned_execution(session, agent, execution_id)

    account = await session.get(Account, execution.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    instance = account.instance

    credential = await session.scalar(
        select(Credential).where(Credential.account_id == account.id)
    )
    credentials = (
        get_cipher(get_settings()).decrypt_dict(credential.data_encrypted)
        if credential is not None
        else {}
    )
    config = {**(instance.config or {}), **(account.config or {})}

    return {
        "execution_id": execution.id,
        "platform_id": instance.platform_id,
        "task_name": execution.task_name,
        "base_url": instance.base_url,
        "config": config,
        "credentials": credentials,
        "http_timeout": get_settings().http_timeout,
    }


@router.post("/tasks/{execution_id}/result")
async def submit_result(
    execution_id: int,
    payload: AgentResultRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """上报执行结果并终结执行（finalize_execution 内部提交事务）。

    执行已不在 RUNNING（如已被离线清扫标记 INTERRUPTED）时仍允许上报，
    结果将覆盖原状态 —— 作为 Agent 迟到结果的恢复路径。
    """
    execution = await _get_owned_execution(session, agent, execution_id)

    try:
        status = TaskStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效状态") from None

    result = TaskResult(
        success=payload.success,
        status=status,
        message=payload.message,
        data=payload.data,
        metrics=payload.metrics,
    )
    await finalize_execution(session, execution, result)
    return {"ok": True, "final_status": execution.status}
