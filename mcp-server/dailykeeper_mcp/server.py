"""DailyKeeper MCP Server（stdio）：``dk-mcp``。

通过 FastMCP 把 DailyKeeper 的状态查询与任务触发能力暴露给 MCP 客户端
（Claude Desktop / Claude Code 等）。所有工具返回格式化 JSON 字符串；
工具描述为中文（展示给 LLM），工具名与参数为英文。
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from dailykeeper_mcp.backend import BackendClient
from dailykeeper_mcp.config import load_config

mcp = FastMCP("dailykeeper")

_backend: BackendClient | None = None


def _b() -> BackendClient:
    """取全局 BackendClient；未初始化时给出中文报错。"""
    global _backend
    if _backend is None:
        raise RuntimeError("MCP server 未初始化")
    return _backend


def _json(data) -> str:
    """序列化为带缩进、不转义中文的 JSON 字符串。"""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@mcp.tool()
async def get_overview() -> str:
    """获取 DailyKeeper 系统总览：账号数、今日任务数、今日成功数、待处理异常、在线 Agent 数、已加载插件数、调度器心跳状态。"""
    return _json(await _b().overview())


@mcp.tool()
async def list_accounts() -> str:
    """列出所有平台账号：平台、实例、状态（ACTIVE/AUTH_EXPIRED/DISABLED）、启用、最近签到日期。"""
    return _json(await _b().accounts())


@mcp.tool()
async def list_scheduled_tasks() -> str:
    """列出定时任务：账号、任务、执行时间、周期、启用、下次执行。"""
    return _json(await _b().scheduled_tasks())


@mcp.tool()
async def list_executions(status: str = "", limit: int = 20) -> str:
    """查询最近任务执行记录（含结果消息与状态）；status 可选过滤（SUCCESS/FAILED/AUTH_EXPIRED/NEEDS_ACTION/RATE_LIMITED/SKIPPED/INTERRUPTED/PENDING/RUNNING）；limit 上限 50（>50 截断到 50）。"""
    limit = min(max(int(limit), 1), 50)
    status = (status or "").strip()
    data = await _b().executions(status=status or None, limit=limit)
    return _json(data)


@mcp.tool()
async def get_execution(execution_id: int) -> str:
    """查询单条执行详情（含完整结果 data/metrics）。"""
    return _json(await _b().execution(int(execution_id)))


@mcp.tool()
async def run_task_now(scheduled_task_id: int) -> str:
    """立即触发一次定时任务（受当日幂等去重保护；返回 created/execution_id/message）。"""
    return _json(await _b().run_task_now(int(scheduled_task_id)))


@mcp.tool()
async def get_resources() -> str:
    """查询资源最新快照总览（余额/积分/魔力/上传下载等，按账号分组）。"""
    return _json(await _b().resources_summary())


def main() -> None:
    """启动 MCP Server（stdio）：读取 ``DK_MCP_*`` 配置并进入事件循环。"""
    global _backend
    config = load_config()
    _backend = BackendClient(config)
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
