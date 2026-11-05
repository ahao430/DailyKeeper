"""M-Team（馒头）PT 站插件：API Key 查询用户信息与魔力。"""

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


class MTeamPlugin(PlatformPlugin):
    """M-Team（馒头）PT 站插件。"""

    plugin_id: ClassVar[str] = "mteam"
    plugin_name: ClassVar[str] = "M-Team"
    plugin_version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = (
        "M-Team（馒头）PT 站：API Key 查询用户信息与魔力；"
        "签到/保活需要浏览器自动化（后续版本，官方 API 访问不计入登录活跃）"
    )
    auth_types: ClassVar[list] = ["api_key"]
    config_schema: ClassVar[list] = [
        FieldDef(
            name="profile_path",
            label="用户信息接口路径",
            type="string",
            required=False,
            default="/api/member/profile",
            help="M-Team 官方 API 路径，通常无需修改",
        ),
    ]
    account_schema: ClassVar[list] = []
    task_definitions: ClassVar[list] = [
        TaskDefinition(name="get_user_info", description="查询用户信息与魔力", default_time="09:00"),
        TaskDefinition(
            name="daily_checkin",
            description="浏览器登录保活（官方 API 不计入登录活跃，待浏览器自动化版本）",
            requires_browser=True,
            default_time="08:30",
            produces_resources=False,
        ),
    ]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        if task_name not in {t.name for t in self.task_definitions}:
            return TaskResult.failed(f"未知任务: {task_name}")

        if task_name == "daily_checkin":
            return TaskResult.needs_action(
                "M-Team 签到/保活需要浏览器自动化（官方 API 访问不计入登录活跃），将在后续版本支持"
            )

        http = context.http
        if http is None:
            return TaskResult.failed("运行时未提供 HTTP 客户端")

        api_key = str((context.credentials or {}).get("api_key") or "")
        if not api_key:
            return TaskResult.auth_expired("未配置 API Key（控制台 → 实验室 → 存取令牌）")

        config = context.config or {}
        http.set_default_headers({"x-api-key": api_key})
        path = str(config.get("profile_path") or "/api/member/profile")

        try:
            return await self._get_user_info(http, path)
        except httpx.TimeoutException:
            return TaskResult.failed("请求超时", retryable=True)
        except httpx.HTTPError as e:
            return TaskResult.failed(f"网络错误: {type(e).__name__}", retryable=True)

    async def _get_user_info(self, http: HttpClient, path: str) -> TaskResult:
        resp = await http.post(path, json={})
        if resp.status_code in (401, 403):
            return TaskResult.auth_expired("API Key 无效或已过期")
        if resp.status_code == 429:
            return TaskResult(
                success=False,
                status=TaskStatus.RATE_LIMITED,
                message="请求过于频繁（HTTP 429）",
            )
        content_type = resp.headers.get("content-type", "")
        if "json" not in content_type.lower():
            return TaskResult.needs_action("站点返回非 JSON 响应")

        payload = resp.json()
        data = payload.get("data") or {}

        # 防御式提取：字段缺失或类型异常时不至于崩溃
        username = str(data.get("username") or data.get("name") or "")
        bonus = self._as_number(data.get("bonus"))
        upload = self._as_number(data.get("uploaded"))
        download = self._as_number(data.get("downloaded"))
        share_rate = self._as_number(data.get("share_rate"))

        resources: list[dict] = []
        if bonus is not None:
            resources.append({"resource_type": "bonus", "value": bonus, "unit": "BOSON"})
        if upload is not None:
            resources.append({"resource_type": "upload", "value": upload, "unit": "bytes"})
        if download is not None:
            resources.append(
                {"resource_type": "download", "value": download, "unit": "bytes"}
            )
        if share_rate is not None:
            resources.append(
                {"resource_type": "share_rate", "value": share_rate, "unit": "x"}
            )

        result_data = {
            "username": username,
            "user_id": data.get("id"),
            # 原始字段名快照，便于排查站点字段差异
            "raw_keys": sorted(data.keys())[:30],
        }
        if resources:
            result_data["resources"] = resources

        return TaskResult.ok(f"用户信息获取成功: {username}", result_data)

    @staticmethod
    def _as_number(value: object) -> float | None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return float(value)
