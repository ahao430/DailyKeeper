"""PlatformPlugin base class and descriptor models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from dailykeeper_sdk.context import TaskContext
from dailykeeper_sdk.result import TaskResult, TaskStatus


@dataclass
class FieldDef:
    """One config field, rendered dynamically by the dashboard as a form field.

    ``options`` 项可以是字符串，也可以是 ``{"value": ..., "label": ...}``——
    后者用于选项值与展示文案不同（如英文枚举配中文标签）的场景。
    """

    name: str
    label: str
    type: str = "string"  # string | secret | number | boolean | select
    required: bool = False
    default: object = None
    options: list | None = None
    help: str = ""
    placeholder: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name, "label": self.label, "type": self.type,
            "required": self.required, "default": self.default,
            "options": self.options, "help": self.help, "placeholder": self.placeholder,
        }


@dataclass
class TaskDefinition:
    """Declaration of one task a plugin can execute."""

    name: str
    description: str = ""
    description_en: str = ""
    requires_browser: bool = False
    requires_agent: bool = False
    default_time: str = "08:30"
    produces_resources: bool = True
    idempotent: bool = True
    allow_concurrent: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "description_en": self.description_en,
            "requires_browser": self.requires_browser,
            "requires_agent": self.requires_agent,
            "default_time": self.default_time,
            "produces_resources": self.produces_resources,
            "idempotent": self.idempotent,
            "allow_concurrent": self.allow_concurrent,
        }


class PlatformPlugin(ABC):
    """Base class for all DailyKeeper platform plugins.

    Subclasses set the ClassVars and implement execute().
    """

    plugin_id: ClassVar[str] = ""
    plugin_name: ClassVar[str] = ""
    plugin_version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = ""
    auth_types: ClassVar[list] = ["cookie"]
    config_schema: ClassVar[list] = []        # list[FieldDef] — 实例级配置
    account_schema: ClassVar[list] = []       # list[FieldDef] — 账号级配置
    credential_schema: ClassVar[list] = []    # list[FieldDef] — 登录凭据字段（Dashboard 据此渲染命名表单）
    task_definitions: ClassVar[list] = []     # list[TaskDefinition]

    def validate_config(self, config: dict) -> tuple[bool, str]:
        """Validate instance-level config; return (ok, error_message)."""
        missing = [
            f.name for f in self.config_schema
            if f.required and not str((config or {}).get(f.name) or "").strip()
        ]
        return (len(missing) == 0, f"缺少必填配置: {', '.join(missing)}" if missing else "")

    def validate_account_config(self, account_config: dict) -> tuple[bool, str]:
        """Validate account-level config against account_schema; return (ok, error_message)."""
        missing = [
            f.name for f in self.account_schema
            if f.required and not str((account_config or {}).get(f.name) or "").strip()
        ]
        return (len(missing) == 0, f"缺少必填账号配置: {', '.join(missing)}" if missing else "")

    @abstractmethod
    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        """Execute a declared task. Must never raise for expected failures; return TaskResult instead."""

    def manifest(self) -> dict:
        """Serialise the plugin declaration for the API/UI (no code execution)."""
        return {
            "plugin_id": self.plugin_id,
            "plugin_name": self.plugin_name,
            "version": self.plugin_version,
            "description": self.description,
            "auth_types": self.auth_types,
            "config_schema": [f.to_dict() for f in self.config_schema],
            "account_schema": [f.to_dict() for f in self.account_schema],
            "credential_schema": [f.to_dict() for f in self.credential_schema],
            "task_definitions": [t.to_dict() for t in self.task_definitions],
            "requires_browser_any": any(t.requires_browser for t in self.task_definitions),
            "requires_agent_any": any(t.requires_agent for t in self.task_definitions),
        }
