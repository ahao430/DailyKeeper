"""服务器 API 客户端：心跳、认领任务、拉取上下文、回传结果。"""

from __future__ import annotations

import httpx

from dailykeeper_agent.config import AgentConfig


class AgentClient:
    """与 DailyKeeper 服务器 ``/api/agent/*`` 接口通信的异步客户端。

    所有请求自动携带 ``X-Agent-Token`` 头。非 2xx 响应统一转为
    :class:`RuntimeError`（消息含状态码与服务器 ``detail``）。
    """

    def __init__(
        self,
        config: AgentConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        if http_client is None:
            self._client = httpx.AsyncClient(
                base_url=config.server_url,
                headers={"X-Agent-Token": config.token},
                timeout=30,
                verify=config.verify_tls,
                trust_env=False,
                follow_redirects=True,
            )
            self._owns_client = True
        else:
            # 依赖注入（测试用 ASGITransport）：仍确保令牌头存在且最新。
            http_client.headers["X-Agent-Token"] = config.token
            self._client = http_client
            self._owns_client = False

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """非 2xx 时抛出带服务器 detail 的 RuntimeError。"""
        if response.is_success:
            return
        try:
            detail = str(response.json().get("detail", ""))
        except ValueError:
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"服务器返回 {response.status_code}{suffix}")

    async def heartbeat(self, version: str, capabilities: list[str]) -> dict:
        """上报心跳；服务器返回心跳间隔与时间。"""
        response = await self._client.post(
            "/api/agent/heartbeat", json={"version": version, "capabilities": capabilities}
        )
        self._raise_for_status(response)
        return response.json()

    async def claim_tasks(self, limit: int) -> list[dict]:
        """认领一批待执行任务（服务器限制单次最多 5 个）。"""
        response = await self._client.post("/api/agent/tasks/claim", json={"limit": limit})
        self._raise_for_status(response)
        data = response.json()
        return data if isinstance(data, list) else []

    async def task_context(self, execution_id: int) -> dict:
        """拉取一个任务的执行上下文（配置、凭据、HTTP 超时等）。"""
        response = await self._client.get(f"/api/agent/tasks/{execution_id}/context")
        self._raise_for_status(response)
        return response.json()

    async def post_result(self, execution_id: int, payload: dict) -> dict:
        """回传任务执行结果。"""
        response = await self._client.post(
            f"/api/agent/tasks/{execution_id}/result", json=payload
        )
        self._raise_for_status(response)
        return response.json()

    async def aclose(self) -> None:
        """关闭底层 HTTP 客户端（依赖注入的客户端不归本实例所有，不关闭）。"""
        if self._owns_client:
            await self._client.aclose()
