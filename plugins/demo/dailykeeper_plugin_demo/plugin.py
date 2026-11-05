"""演示平台插件：模拟各种任务结果，验证任务引擎闭环。"""

from __future__ import annotations

from typing import ClassVar

from dailykeeper_sdk import (
    FieldDef,
    PlatformPlugin,
    TaskContext,
    TaskDefinition,
    TaskResult,
    TaskStatus,
)

_BEHAVIORS = [
    "success",
    "auth_expired",
    "fail_retryable",
    "fail_fatal",
    "needs_action",
    "skip",
    "rate_limited",
]


class DemoPlugin(PlatformPlugin):
    """模拟平台插件，不发起任何网络请求。"""

    plugin_id: ClassVar[str] = "demo"
    plugin_name: ClassVar[str] = "演示平台"
    plugin_version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = (
        "模拟平台插件：验证任务引擎闭环（调度→执行→去重→结果→通知），测试用"
    )
    auth_types: ClassVar[list] = ["none"]
    config_schema: ClassVar[list] = []
    account_schema: ClassVar[list] = [
        FieldDef(
            name="behavior",
            label="行为模式",
            type="select",
            required=False,
            default="success",
            options=_BEHAVIORS,
            help="执行行为，用于测试各种任务结果",
        ),
        FieldDef(
            name="balance",
            label="余额",
            type="number",
            required=False,
            default=0,
            help=">0 时在结果中生成余额快照",
        ),
        FieldDef(name="points", label="积分", type="number", required=False, default=0),
        FieldDef(
            name="balance_unit",
            label="余额单位",
            type="string",
            required=False,
            default="CNY",
        ),
    ]
    task_definitions: ClassVar[list] = [
        TaskDefinition(
            name="daily_checkin",
            description="每日签到",
            default_time="08:10",
            produces_resources=False,
        ),
        TaskDefinition(name="get_user_info", description="查询用户信息", default_time="09:00"),
        TaskDefinition(
            name="browser_probe",
            description="浏览器探针（打开页面读取标题，验证浏览器 Worker 链路）",
            requires_browser=True,
            default_time="10:00",
            produces_resources=False,
        ),
        TaskDefinition(
            name="agent_probe",
            description="Agent 探针（在本地执行端回显配置，验证 Agent 链路）",
            requires_agent=True,
            default_time="10:30",
            produces_resources=False,
        ),
    ]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        if task_name not in {t.name for t in self.task_definitions}:
            return TaskResult.failed(f"未知任务: {task_name}")
        if task_name == "browser_probe":
            return await self._execute_browser_probe(context)
        if task_name == "agent_probe":
            return self._execute_agent_probe(context)

        config = context.config or {}
        behavior = str(config.get("behavior") or "success")
        msg = str(config.get("message") or "")

        if behavior == "auth_expired":
            result = TaskResult.auth_expired(msg or "演示：登录状态已失效")
        elif behavior == "fail_retryable":
            result = TaskResult.failed(msg or "演示：可重试失败（模拟网络错误）", retryable=True)
        elif behavior == "fail_fatal":
            result = TaskResult.failed(msg or "演示：不可重试失败", retryable=False)
        elif behavior == "needs_action":
            result = TaskResult.needs_action(msg or "演示：需要人工处理")
        elif behavior == "skip":
            result = TaskResult(
                success=False,
                status=TaskStatus.SKIPPED,
                message=msg or "演示：今日已签到，跳过",
            )
        elif behavior == "rate_limited":
            result = TaskResult(
                success=False,
                status=TaskStatus.RATE_LIMITED,
                message=msg or "演示：触发限流",
            )
        else:
            default_msg = "演示签到成功" if task_name == "daily_checkin" else "演示任务执行成功"
            result = TaskResult.ok(msg or default_msg)

        if result.success:
            resources = self._build_resources(config)
            if resources:
                result.data["resources"] = resources
        return result

    async def _execute_browser_probe(self, context: TaskContext) -> TaskResult:
        """打开探针页面读取标题，验证浏览器执行链路（无外部网络依赖）。"""
        if context.browser is None:
            return TaskResult.needs_action("浏览器会话未注入（应由浏览器 Worker 执行）")
        probe_url = str(
            (context.config or {}).get("probe_url")
            or "data:text/html,<html><head><title>dailykeeper-probe-ok</title></head><body>probe</body></html>"
        )
        try:
            await context.browser.goto(probe_url)
            title = await context.browser.page.title()
        except Exception as exc:  # noqa: BLE001 - 浏览器异常统一转失败
            return TaskResult.failed(f"浏览器探针失败: {exc}", retryable=True)
        if "dailykeeper-probe" not in title:
            return TaskResult.failed(f"浏览器探针标题异常: {title}", retryable=False)
        return TaskResult.ok(
            f"浏览器探针成功: {title}",
            data={"title": title, "url": context.browser.url},
        )

    def _execute_agent_probe(self, context: TaskContext) -> TaskResult:
        """回显配置，验证本地 Agent 执行链路（不依赖 context.http/browser）。"""
        config = context.config or {}
        echo = str(config.get("agent_echo") or "pong")
        import platform as _platform

        return TaskResult.ok(
            f"Agent 探针成功: {echo}",
            data={
                "echo": echo,
                "runner_hostname": _platform.node(),
                "runner_python": _platform.python_version(),
                "platform_id": context.platform_id,
            },
        )

    def _build_resources(self, config: dict) -> list[dict]:
        """按账号配置构造资源快照（余额/积分，值 >0 时才生成）。"""
        balance = self._as_number(config.get("balance"))
        points = self._as_number(config.get("points"))
        if balance is None and points is None:
            return []

        unit = str(config.get("balance_unit") or "CNY")
        resources: list[dict] = []
        if balance is not None and balance > 0:
            resources.append(
                {"resource_type": "balance", "value": balance, "unit": unit}
            )
        if points is not None and points > 0:
            resources.append({"resource_type": "points", "value": points, "unit": "points"})
        return resources

    @staticmethod
    def _as_number(value: object) -> float | None:
        """把配置值转成 float；缺失或非法时返回 None。"""
        if value is None or value == "":
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
