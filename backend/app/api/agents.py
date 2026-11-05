"""本地 Agent 管理：注册、列表、删除与令牌轮换（管理端，需管理员登录）。

Agent 令牌只在创建/轮换时明文返回一次，服务端仅保存 SHA-256 摘要。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.core.security import random_token
from app.core.timeutil import now_utc
from app.models import Agent, TaskExecution, TaskResultRecord
from app.services.task_engine import AGENT_OFFLINE_SECONDS

router = APIRouter(
    prefix="/api/agents", tags=["agents"], dependencies=[Depends(get_current_admin)]
)


class CreateAgentRequest(BaseModel):
    name: str


def _hash_token(token: str) -> str:
    """Agent 令牌的存储摘要：SHA-256 十六进制（令牌本身为高熵随机串）。"""
    return hashlib.sha256(token.encode()).hexdigest()


def _dt(value: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601; None stays None."""
    return value.isoformat() if value is not None else None


def _is_online(agent: Agent, now: datetime) -> bool:
    """在线判定：最近一次心跳在离线窗口内（默认 90 秒）。"""
    return (
        agent.last_heartbeat is not None
        and agent.last_heartbeat >= now - timedelta(seconds=AGENT_OFFLINE_SECONDS)
    )


async def _get_agent_or_404(session: AsyncSession, agent_id: int) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return agent


async def _running_task_counts(session: AsyncSession) -> dict[int, int]:
    """每个 Agent 当前 RUNNING 的执行数量（按 assigned_agent_id 分组）。"""
    rows = (
        await session.execute(
            select(TaskExecution.assigned_agent_id, func.count())
            .where(
                TaskExecution.status == "RUNNING",
                TaskExecution.assigned_agent_id.isnot(None),
            )
            .group_by(TaskExecution.assigned_agent_id)
        )
    ).all()
    return {agent_id: count for agent_id, count in rows}


@router.get("")
async def list_agents(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """所有 Agent 及其在线状态与运行中任务数。"""
    now = now_utc()
    agents = (await session.scalars(select(Agent).order_by(Agent.id))).all()
    running = await _running_task_counts(session)
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "version": agent.version,
            "last_heartbeat": _dt(agent.last_heartbeat),
            "online": _is_online(agent, now),
            "meta": agent.meta,
            "created_at": _dt(agent.created_at),
            "running_tasks": running.get(agent.id, 0),
        }
        for agent in agents
    ]


@router.post("")
async def create_agent(payload: CreateAgentRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """注册一个 Agent 并生成令牌；令牌仅此一次明文返回。"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Agent 名称不能为空")

    duplicate = await session.scalar(
        select(Agent.id).where(Agent.name == name).limit(1)
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Agent 名称已存在")

    token = random_token(32)
    agent = Agent(name=name, token_hash=_hash_token(token), status="OFFLINE")
    session.add(agent)
    await session.commit()
    return {
        "id": agent.id,
        "name": agent.name,
        "token": token,
        "note": "令牌仅显示一次，请立即配置到 Agent",
    }


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    """删除 Agent：其运行中执行标记中断，历史执行保留（引用置空）。"""
    agent = await _get_agent_or_404(session, agent_id)
    now = now_utc()

    running = (
        await session.scalars(
            select(TaskExecution).where(
                TaskExecution.assigned_agent_id == agent_id,
                TaskExecution.status == "RUNNING",
            )
        )
    ).all()
    for execution in running:
        execution.status = "INTERRUPTED"
        execution.finished_at = now
        session.add(
            TaskResultRecord(
                execution_id=execution.id,
                success=False,
                status="INTERRUPTED",
                message="Agent 已被删除，任务中断",
            )
        )

    # 先解除全部执行记录对该 Agent 的外键引用，再删除行（SQLite 开启外键约束）
    await session.execute(
        update(TaskExecution)
        .where(TaskExecution.assigned_agent_id == agent_id)
        .values(assigned_agent_id=None)
        .execution_options(synchronize_session=False)
    )
    await session.delete(agent)
    await session.commit()
    return {"ok": True}


@router.post("/{agent_id}/rotate")
async def rotate_agent_token(agent_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    """轮换 Agent 令牌：旧令牌立即失效，新令牌仅此一次明文返回。"""
    agent = await _get_agent_or_404(session, agent_id)
    token = random_token(32)
    agent.token_hash = _hash_token(token)
    await session.commit()
    return {
        "id": agent.id,
        "token": token,
        "note": "令牌仅显示一次，请立即更新到 Agent（旧令牌已失效）",
    }
