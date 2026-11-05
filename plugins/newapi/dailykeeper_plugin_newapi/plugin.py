"""NewAPI/OneAPI 系中转站插件：签到、用户信息与余额查询。"""

from __future__ import annotations

from typing import ClassVar

import httpx

from dailykeeper_sdk import (
    FieldDef,
    HttpClient,
    PlatformPlugin,
    TaskContext,
    TaskDefinition,
    TaskResult,
    TaskStatus,
)

# 登录失效时业务 message 中常见的关键词
_LOGIN_EXPIRED_KEYWORDS = ("未登录", "请先登录", "登录", "401", "unauthorized", "无权")


class NewApiPlugin(PlatformPlugin):
    """NewAPI/OneAPI 系中转站插件。"""

    plugin_id: ClassVar[str] = "newapi"
    plugin_name: ClassVar[str] = "NewAPI 中转站"
    plugin_version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = (
        "NewAPI/OneAPI 系中转站：每日签到、用户信息与余额查询（接口路径按站点可配置）"
    )
    auth_types: ClassVar[list] = ["token", "cookie"]
    config_schema: ClassVar[list] = [
        FieldDef(
            name="checkin_path",
            label="签到接口路径",
            type="string",
            required=False,
            default="/api/user/sign_in",
            help="各站点可能不同，如 /api/user/check_in；留空表示站点无签到功能",
        ),
        FieldDef(
            name="user_info_path",
            label="用户信息接口路径",
            type="string",
            required=False,
            default="/api/user/self",
        ),
        FieldDef(
            name="quota_per_unit",
            label="quota 兑换比例",
            type="number",
            required=False,
            default=500000,
            help="多少 quota 等于 1 美元，NewAPI 默认 500000",
        ),
    ]
    account_schema: ClassVar[list] = [
        FieldDef(
            name="api_user",
            label="用户 ID（new-api-user）",
            type="string",
            required=False,
            help="new-api-user 请求头的值（站点用户 ID），多数站点必填",
        ),
    ]
    task_definitions: ClassVar[list] = [
        TaskDefinition(name="daily_checkin", description="每日签到", default_time="08:10"),
        TaskDefinition(name="get_user_info", description="查询用户信息与余额", default_time="09:00"),
    ]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        if task_name not in {t.name for t in self.task_definitions}:
            return TaskResult.failed(f"未知任务: {task_name}")

        credentials = context.credentials or {}
        config = context.config or {}
        http = context.http
        if http is None:
            return TaskResult.failed("运行时未提供 HTTP 客户端")

        auth_result = self._apply_auth(http, credentials, config)
        if auth_result is not None:
            return auth_result

        try:
            if task_name == "get_user_info":
                return await self._get_user_info(http, config)
            return await self._daily_checkin(http, config)
        except httpx.TimeoutException:
            return TaskResult.failed("请求超时", retryable=True)
        except httpx.HTTPError as e:
            return TaskResult.failed(f"网络错误: {type(e).__name__}", retryable=True)

    def _apply_auth(
        self, http: HttpClient, credentials: dict, config: dict
    ) -> TaskResult | None:
        """应用认证信息；缺少认证材料时返回 auth_expired 结果。"""
        token = str(credentials.get("token") or "")
        cookie = str(credentials.get("cookie") or "")
        if not token and not cookie:
            return TaskResult.auth_expired("未配置认证凭据（token 或 cookie）")

        if token:
            http.set_default_headers({"Authorization": f"Bearer {token}"})
        if cookie:
            http.set_cookies(cookie_string=cookie)
        api_user = str(config.get("api_user") or "")
        if api_user:
            http.set_default_headers({"new-api-user": api_user})
        return None

    @staticmethod
    def _is_json_response(resp: httpx.Response) -> bool:
        content_type = resp.headers.get("content-type", "")
        return "json" in content_type.lower()

    async def _get_user_info(self, http: HttpClient, config: dict) -> TaskResult:
        """查询用户信息（网络异常由 execute 统一处理）。"""
        path = str(config.get("user_info_path") or "/api/user/self")
        resp = await http.get(path)
        if resp.status_code in (401, 403):
            return TaskResult.auth_expired(f"认证失败（HTTP {resp.status_code}）")
        if resp.status_code == 429:
            return TaskResult(
                success=False,
                status=TaskStatus.RATE_LIMITED,
                message="请求过于频繁（HTTP 429）",
            )
        if not self._is_json_response(resp):
            return TaskResult.needs_action(
                "站点返回非 JSON 响应，可能被 WAF 拦截或接口路径有误"
            )

        payload = resp.json()
        if payload.get("success") is False:
            message = str(payload.get("message") or "")
            if any(k in message for k in _LOGIN_EXPIRED_KEYWORDS):
                return TaskResult.auth_expired(f"登录状态失效: {message}")
            return TaskResult.failed(f"接口返回失败: {message}")

        data = payload.get("data") or {}
        user_id = data.get("id")
        api_user = str(config.get("api_user") or "")
        if not api_user and user_id:
            # 拿到真实用户 ID 后，为同一执行内的后续请求补上 new-api-user 头
            http.set_default_headers({"new-api-user": str(user_id)})

        quota = data.get("quota")
        used_quota = data.get("used_quota")
        qpu = self._as_number(config.get("quota_per_unit")) or 0.0

        metrics: dict = {}
        resources: list[dict] = []
        if isinstance(quota, (int, float)) and isinstance(used_quota, (int, float)):
            metrics = {"quota": quota, "used_quota": used_quota}
            if qpu > 0:
                resources.append(
                    {
                        "resource_type": "balance",
                        "value": round(float(quota) / qpu, 4),
                        "unit": "USD",
                    }
                )
                resources.append(
                    {
                        "resource_type": "usage",
                        "value": round(float(used_quota) / qpu, 4),
                        "unit": "USD",
                    }
                )

        result_data: dict = {"user_id": user_id}
        if resources:
            result_data["resources"] = resources

        display = data.get("username") or user_id or "未知用户"
        return TaskResult.ok(
            f"用户信息获取成功: {display}", result_data, metrics
        )

    async def _daily_checkin(self, http: HttpClient, config: dict) -> TaskResult:
        # 留空表示站点无签到功能（路径本身完全可配置，可含 query 串）
        path = str(config.get("checkin_path") or "").strip()
        if not path:
            return TaskResult(
                success=False,
                status=TaskStatus.SKIPPED,
                message="站点未配置签到接口路径，跳过签到",
            )

        # 部分站点签到需带 turnstile 等参数，path 完全可配置（可含 query 串）覆盖该差异
        resp = await http.post(path, json={})
        if resp.status_code in (401, 403):
            return TaskResult.auth_expired(f"认证失败（HTTP {resp.status_code}）")
        if resp.status_code == 429:
            return TaskResult(
                success=False,
                status=TaskStatus.RATE_LIMITED,
                message="请求过于频繁（HTTP 429）",
            )
        if not self._is_json_response(resp):
            return TaskResult.needs_action(
                "站点返回非 JSON 响应，可能被 WAF 拦截或接口路径有误"
            )

        payload = resp.json()
        if payload.get("success") is True:
            return TaskResult.ok(str(payload.get("message") or "签到成功"))

        message = str(payload.get("message") or "")
        if "已" in message:
            return TaskResult(
                success=False,
                status=TaskStatus.SKIPPED,
                message=f"站点返回: {message}",
            )
        return TaskResult.failed(f"签到失败: {message}", retryable=False)

    @staticmethod
    def _as_number(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
