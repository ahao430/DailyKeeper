"""Task result model shared by all DailyKeeper plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    """Unified task status (see project plan)."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    NEEDS_ACTION = "NEEDS_ACTION"
    RATE_LIMITED = "RATE_LIMITED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    INTERRUPTED = "INTERRUPTED"


@dataclass
class TaskResult:
    """Unified result returned by a plugin task execution."""

    success: bool
    status: TaskStatus
    message: str = ""
    data: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", data: dict | None = None, metrics: dict | None = None) -> "TaskResult":
        return cls(
            success=True,
            status=TaskStatus.SUCCESS,
            message=message,
            data=data or {},
            metrics=metrics or {},
        )

    @classmethod
    def failed(cls, message: str = "", retryable: bool = False, metrics: dict | None = None) -> "TaskResult":
        return cls(
            success=False,
            status=TaskStatus.FAILED,
            message=message,
            data={"retryable": retryable},
            metrics=metrics or {},
        )

    @classmethod
    def auth_expired(cls, message: str = "登录状态已失效，请更新凭据") -> "TaskResult":
        return cls(success=False, status=TaskStatus.AUTH_EXPIRED, message=message)

    @classmethod
    def needs_action(cls, message: str = "需要人工处理") -> "TaskResult":
        return cls(success=False, status=TaskStatus.NEEDS_ACTION, message=message)
