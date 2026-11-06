"""NexusPHP 论坛/PT 站点插件：Cookie 每日签到。"""

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

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class NexusPHPPlugin(PlatformPlugin):
    """NexusPHP 论坛/PT 站点插件。"""

    plugin_id: ClassVar[str] = "nexusphp"
    plugin_name: ClassVar[str] = "NexusPHP 站点"
    plugin_version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = (
        "NexusPHP 论坛/PT 站点：Cookie 每日签到（attendance.php），"
        "成功/已签/登录失效标记可配置"
    )
    auth_types: ClassVar[list] = ["cookie"]
    config_schema: ClassVar[list] = [
        FieldDef(
            name="checkin_path",
            label="签到页面路径",
            type="string",
            required=False,
            default="/attendance.php",
        ),
        FieldDef(
            name="success_marker",
            label="成功标记",
            type="string",
            required=False,
            default="签到成功",
        ),
        FieldDef(
            name="already_marker",
            label="已签到标记",
            type="string",
            required=False,
            default="已签到",
        ),
        FieldDef(
            name="user_agent",
            label="User-Agent",
            type="string",
            required=False,
            default=_DEFAULT_USER_AGENT,
        ),
    ]
    credential_schema: ClassVar[list] = [
        FieldDef(
            name="cookie",
            label="Cookie",
            type="secret",
            required=True,
            help="浏览器登录后的完整 Cookie",
        ),
    ]
    account_schema: ClassVar[list] = []
    task_definitions: ClassVar[list] = [
        TaskDefinition(name="daily_checkin", description="每日签到", default_time="08:30"),
    ]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        if task_name not in {t.name for t in self.task_definitions}:
            return TaskResult.failed(f"未知任务: {task_name}")

        cookie = str((context.credentials or {}).get("cookie") or "")
        if not cookie:
            return TaskResult.auth_expired("未配置 Cookie")

        http = context.http
        if http is None:
            return TaskResult.failed("运行时未提供 HTTP 客户端")

        config = context.config or {}
        http.set_cookies(cookie_string=cookie)
        http.set_default_headers(
            {"User-Agent": str(config.get("user_agent") or _DEFAULT_USER_AGENT)}
        )
        path = str(config.get("checkin_path") or "/attendance.php")
        success_marker = str(config.get("success_marker") or "签到成功")
        already_marker = str(config.get("already_marker") or "已签到")

        try:
            resp = await http.get(path)
        except httpx.TimeoutException:
            return TaskResult.failed("请求超时", retryable=True)
        except httpx.HTTPError as e:
            return TaskResult.failed(f"网络错误: {type(e).__name__}", retryable=True)

        text = resp.text
        # 登录失效：站点通常重定向到 login.php 或在页面中提示登录
        if "请登录" in text or "login.php" in str(resp.url):
            return TaskResult.auth_expired("登录状态失效（被重定向到登录页）")

        if success_marker and success_marker in text:
            return TaskResult.ok("签到成功")
        if already_marker and already_marker in text:
            return TaskResult(
                success=False,
                status=TaskStatus.SKIPPED,
                message="今日已签到，跳过",
            )
        return TaskResult.failed(
            f"未识别到签到结果标记，页面片段: {text[:120]}", retryable=False
        )
