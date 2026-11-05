"""Alembic migration environment for DailyKeeper (sync engine).

The application runs on an async driver (``sqlite+aiosqlite``), but
migrations use the plain sync driver: ``+aiosqlite`` is stripped from the
resolved URL before connecting.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models.tables import Base

# The Alembic Config object, which provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini when one is present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata used by --autogenerate.
target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the sync database URL for migrations.

    Preference order: DAILYKEEPER_DATABASE_URL env var, then the default
    from app settings. Async drivers are converted to their sync
    counterparts (e.g. ``sqlite+aiosqlite`` -> ``sqlite``).
    """
    url = os.environ.get("DAILYKEEPER_DATABASE_URL") or get_settings().database_url
    return url.replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL; no DBAPI is required. SQL is
    emitted to stdout without touching a database.
    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
    # configparser interpolation requires literal '%' to be escaped.
    config.set_main_option("sqlalchemy.url", _database_url().replace("%", "%%"))

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
