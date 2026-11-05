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
    ]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        if task_name not in {t.name for t in self.task_definitions}:
            return TaskResult.failed(f"未知任务: {task_name}")

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
