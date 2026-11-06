"""SQLAlchemy ORM models for DailyKeeper.

All datetime columns store naive UTC values; per-site timezone handling
lives in ``app.core.timeutil``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Account status constants
ACCOUNT_STATUS_ACTIVE = "ACTIVE"
ACCOUNT_STATUS_AUTH_EXPIRED = "AUTH_EXPIRED"
ACCOUNT_STATUS_DISABLED = "DISABLED"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class Platform(Base):
    """A registered platform plugin (``id`` equals the plugin_id)."""

    __tablename__ = "platforms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    auth_types: Mapped[list] = mapped_column(JSON, default=list)
    config_schema: Mapped[list] = mapped_column(JSON, default=list)
    account_schema: Mapped[list] = mapped_column(JSON, default=list)
    task_definitions: Mapped[list] = mapped_column(JSON, default=list)
    credential_schema: Mapped[list | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="entry_point")


class PlatformInstance(Base):
    """A concrete deployment of a platform (site URL + config)."""

    __tablename__ = "platform_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_id: Mapped[str] = mapped_column(ForeignKey("platforms.id"))
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str] = mapped_column(String(512), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    platform: Mapped["Platform"] = relationship(lazy="joined")
    accounts: Mapped[list["Account"]] = relationship(back_populates="instance")


class Account(Base):
    """A platform account managed by DailyKeeper."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("platform_instances.id"))
    name: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default=ACCOUNT_STATUS_ACTIVE)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_task_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checkin_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    instance: Mapped["PlatformInstance"] = relationship(back_populates="accounts", lazy="joined")
    credential: Mapped["Credential | None"] = relationship(back_populates="account", uselist=False)


class Credential(TimestampMixin, Base):
    """Encrypted login credentials for an account (one per account)."""

    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(32), default="cookie")
    data_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    account: Mapped["Account"] = relationship(back_populates="credential")


class ScheduledTask(Base):
    """A recurring task configured for one account."""

    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        UniqueConstraint("account_id", "task_name", name="uq_scheduled_tasks_account_task"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    task_name: Mapped[str] = mapped_column(String(64))
    time_of_day: Mapped[str] = mapped_column(String(5), default="08:30")
    interval_days: Mapped[int] = mapped_column(Integer, default=1)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskExecution(Base):
    """One execution attempt of a task for an account.

    Status values: PENDING / RUNNING / SUCCESS / FAILED / SKIPPED /
    INTERRUPTED / AUTH_EXPIRED / NEEDS_ACTION / RATE_LIMITED.
    """

    __tablename__ = "task_executions"
    __table_args__ = (
        Index("ix_task_executions_status_due", "status", "due_at"),
        Index("ix_task_executions_dedupe", "account_id", "task_name", "business_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    scheduled_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_tasks.id"), nullable=True
    )
    task_name: Mapped[str] = mapped_column(String(64))
    business_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    needs_browser: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_agent: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id"), nullable=True
    )
    worker_id: Mapped[str] = mapped_column(String(64), default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class TaskResultRecord(Base):
    """Structured result payload attached to one execution."""

    __tablename__ = "task_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("task_executions.id"), unique=True)
    success: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class ResourceSnapshot(Base):
    """A resource value observed for an account at a point in time.

    Numeric values go into ``value``; non-numeric ones (e.g. reset_at) go
    into ``text_value``.
    """

    __tablename__ = "resource_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_executions.id"), nullable=True
    )
    resource_type: Mapped[str] = mapped_column(String(32))
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    text_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str] = mapped_column(String(16), default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)


class NotificationRecord(Base):
    """A notification dispatched (or skipped) by the notifier.

    Status values: SKIPPED / SENT / FAILED.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    channels: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="SKIPPED")


class SystemSetting(Base):
    """A server-level key/value setting stored as JSON."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class User(TimestampMixin, Base):
    """A management-console user (admin account).

    ``password_hash`` stores a PBKDF2 hash; disabled users' JWTs stop
    working immediately because tokens are resolved against this table.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16), default="admin")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Agent(TimestampMixin, Base):
    """A registered worker agent (placeholder for a later phase)."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    token_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="OFFLINE")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
