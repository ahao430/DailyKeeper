"""SDK 单元测试：插件注册表、TaskResult 构造器、HttpClient、描述模型与时间工具。"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from dailykeeper_sdk import (
    FieldDef,
    HttpClient,
    PlatformPlugin,
    TaskDefinition,
    TaskResult,
    TaskStatus,
)
from dailykeeper_plugin_demo.plugin import DemoPlugin
from dailykeeper_sdk.registry import PluginRegistry

from app.core.timeutil import date_in_tz, next_occurrence, parse_hhmm


class _NoPluginId(PlatformPlugin):
    """缺少 plugin_id 的插件类，注册时应被拒绝。"""

    plugin_id = ""
    plugin_name = "无 ID 插件"

    async def execute(self, task_name, context):
        return TaskResult.ok()


# ---------- 插件注册表 ----------


def test_registry_register_and_lookup():
    registry = PluginRegistry()
    instance = registry.register(DemoPlugin)
    assert registry.has("demo")
    plugin = registry.get("demo")
    assert plugin is instance
    assert plugin.plugin_id == "demo"


def test_registry_manifest_keys():
    registry = PluginRegistry()
    registry.register(DemoPlugin)
    manifest = registry.get("demo").manifest()
    for key in (
        "plugin_id",
        "plugin_name",
        "version",
        "description",
        "auth_types",
        "config_schema",
        "account_schema",
        "task_definitions",
        "requires_browser_any",
    ):
        assert key in manifest


def test_registry_duplicate_same_class_ok():
    registry = PluginRegistry()
    registry.register(DemoPlugin)
    registry.register(DemoPlugin)  # 同一插件类重复注册不应抛异常
    assert registry.has("demo")


def test_registry_rejects_missing_plugin_id():
    registry = PluginRegistry()
    with pytest.raises(ValueError):
        registry.register(_NoPluginId)


# ---------- TaskResult 构造器 ----------


def test_task_result_ok():
    result = TaskResult.ok("成功", data={"x": 1}, metrics={"ms": 10})
    assert result.success is True
    assert result.status is TaskStatus.SUCCESS
    assert result.data == {"x": 1}
    assert result.metrics == {"ms": 10}


def test_task_result_failed_retryable():
    result = TaskResult.failed("模拟网络错误", retryable=True)
    assert result.success is False
    assert result.status is TaskStatus.FAILED
    assert result.data["retryable"] is True


def test_task_result_failed_not_retryable():
    result = TaskResult.failed("致命错误", retryable=False)
    assert result.data["retryable"] is False


def test_task_result_auth_expired():
    result = TaskResult.auth_expired()
    assert result.success is False
    assert result.status is TaskStatus.AUTH_EXPIRED


def test_task_result_needs_action():
    result = TaskResult.needs_action("需要人工处理")
    assert result.success is False
    assert result.status is TaskStatus.NEEDS_ACTION


# ---------- HttpClient ----------


def test_http_client_parse_cookie_string():
    assert HttpClient._parse_cookie_string("a=1; b=2") == {"a": "1", "b": "2"}
    assert HttpClient._parse_cookie_string("") == {}
    assert HttpClient._parse_cookie_string(None) == {}


# ---------- 描述模型 ----------


def test_task_definition_to_dict_keys():
    task_def = TaskDefinition(name="daily_checkin", requires_browser=True)
    payload = task_def.to_dict()
    for key in (
        "name",
        "description",
        "description_en",
        "requires_browser",
        "default_time",
        "produces_resources",
        "idempotent",
        "allow_concurrent",
    ):
        assert key in payload
    assert payload["name"] == "daily_checkin"
    assert payload["requires_browser"] is True


def test_field_def_to_dict_keys():
    field = FieldDef(name="behavior", label="行为模式", type="select", options=["success"])
    payload = field.to_dict()
    for key in (
        "name",
        "label",
        "type",
        "required",
        "default",
        "options",
        "help",
        "placeholder",
    ):
        assert key in payload
    assert payload["name"] == "behavior"
    assert payload["options"] == ["success"]


# ---------- 时间工具 ----------


def test_next_occurrence_today_not_passed():
    # 2026-11-05 23:00 UTC = 2026-11-06 07:00 上海时间，当天 08:30 尚未到
    after = datetime(2026, 11, 5, 23, 0)
    assert next_occurrence("08:30", 1, "Asia/Shanghai", after=after) == datetime(
        2026, 11, 6, 0, 30
    )


def test_next_occurrence_today_passed():
    # 2026-11-06 01:00 UTC = 09:00 上海时间，当天 08:30 已过 → 明天 08:30
    after = datetime(2026, 11, 6, 1, 0)
    assert next_occurrence("08:30", 1, "Asia/Shanghai", after=after) == datetime(
        2026, 11, 7, 0, 30
    )


def test_next_occurrence_interval_seven_days():
    after = datetime(2026, 11, 6, 1, 0)
    assert next_occurrence("08:30", 7, "Asia/Shanghai", after=after) == datetime(
        2026, 11, 13, 0, 30
    )


def test_parse_hhmm():
    assert parse_hhmm("8:30") == time(8, 30)
    assert parse_hhmm("08:30") == time(8, 30)
    assert parse_hhmm("00:00") == time(0, 0)
    with pytest.raises(ValueError):
        parse_hhmm("25:00")
    with pytest.raises(ValueError):
        parse_hhmm("abc")


def test_date_in_tz():
    assert isinstance(date_in_tz("Asia/Shanghai"), date)
