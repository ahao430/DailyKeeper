"""DailyKeeper 后端 API 客户端：登录、令牌续期与只读/触发接口封装。

- 认证：优先使用静态令牌（``config.token``）；否则首次调用时用用户名密码
  调 ``POST /api/auth/login`` 换取 ``access_token``。
- 令牌失效：请求返回 401 且配置了用户名密码时，清空令牌重新登录一次并重试；
  仍 401（或没有用户名密码可用）则抛出中文 :class:`RuntimeError`。
- 依赖注入：``http_client`` 参数供测试注入 ASGITransport 客户端，注入的
  客户端生命周期归调用方，:meth:`aclose` 不会关闭它。
"""

from __future__ import annotations

import httpx

from dailykeeper_mcp.config import McpConfig


class BackendClient:
    """与 DailyKeeper 后端 ``/api/*`` 通信的异步客户端（Bearer 认证）。"""

    def __init__(
        self,
        config: McpConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._token: str = config.token  # 可能为空 → 首次调用时登录
        if http_client is None:
            self._client = httpx.AsyncClient(
                base_url=config.server_url,
                timeout=config.request_timeout,
                trust_env=False,
                follow_redirects=True,
            )
            self._owns_client = True
        else:
            self._client = http_client
            self._owns_client = False

    # ---------- 内部工具 ----------

    async def _login(self) -> None:
        """用用户名密码登录并缓存 ``access_token``。"""
        response = await self._client.post(
            "/api/auth/login",
            json={"username": self._config.username, "password": self._config.password},
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"服务器返回 {response.status_code}: 登录失败，请检查 DK_MCP_USERNAME/DK_MCP_PASSWORD"
            )
        self._token = str(response.json().get("access_token") or "")

    async def _ensure_token(self) -> None:
        """没有可用令牌时先登录换取令牌。"""
        if not self._token:
            await self._login()

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            return str(response.json().get("detail", ""))
        except ValueError:
            return ""

    async def _request(self, method: str, path: str, *, json_body: dict | None = None):
        """带认证执行一次请求并解析 JSON。

        流程：确保令牌 → 携带 Bearer 请求 → 401 且配置了用户名密码时清令牌
        重新登录一次并重试 → 最终 401 报“认证失败”，其他非 2xx 报服务器 detail。
        """
        await self._ensure_token()
        response = await self._client.request(
            method,
            path,
            json=json_body,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if response.status_code == 401 and self._config.username and self._config.password:
            # 令牌过期/被替换：重新登录一次并重试
            self._token = ""
            await self._login()
            response = await self._client.request(
                method,
                path,
                json=json_body,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        if response.status_code == 401:
            raise RuntimeError("认证失败，请检查 DK_MCP_TOKEN 或用户名密码")
        if not response.is_success:
            detail = self._detail(response)
            raise RuntimeError(f"服务器返回 {response.status_code}: {detail}")
        return response.json()

    # ---------- API 方法 ----------

    async def overview(self) -> dict:
        """系统总览：版本、账号数、今日执行数与调度器心跳。"""
        return await self._request("GET", "/api/system/info")

    async def accounts(self) -> list[dict]:
        """全部平台账号（含状态与凭据元信息）。"""
        return await self._request("GET", "/api/accounts")

    async def scheduled_tasks(self) -> list[dict]:
        """全部定时任务。"""
        return await self._request("GET", "/api/scheduled-tasks")

    async def executions(
        self,
        status: str | None = None,
        account_id: int | None = None,
        task_name: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """最近的执行记录（可按状态/账号/任务过滤）。"""
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        if account_id is not None:
            params["account_id"] = account_id
        if task_name:
            params["task_name"] = task_name
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return await self._request("GET", f"/api/executions?{query}")

    async def execution(self, execution_id: int) -> dict:
        """单条执行详情（含完整结果 data/metrics）。"""
        return await self._request("GET", f"/api/executions/{execution_id}")

    async def run_task_now(self, scheduled_task_id: int) -> dict:
        """立即触发一次定时任务（受当日幂等去重保护）。"""
        return await self._request("POST", f"/api/scheduled-tasks/{scheduled_task_id}/run-now")

    async def resources_summary(self) -> list[dict]:
        """资源最新快照总览（按账号分组）。"""
        return await self._request("GET", "/api/resources/summary")

    async def aclose(self) -> None:
        """关闭自建客户端；注入的客户端归调用方，不关闭。"""
        if self._owns_client:
            await self._client.aclose()
