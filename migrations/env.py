"""Async Alembic environment for the shared PostgreSQL instance."""

import asyncio
import os
import selectors
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from bid_system.platform.database.models import OrmBase
from bid_system.platform.database.outbox import OutboxEventModel

DATABASE_URL_ENV = "DATABASE_URL"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# WHY: importing each infrastructure model is the explicit migration registry; domain modules
# remain independent of SQLAlchemy and no database connection is opened during import.
registered_models = (OutboxEventModel,)
target_metadata = OrmBase.metadata


def _database_url() -> str:
    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is required for database migrations")
    return url


def run_migrations_offline() -> None:
    """Generate SQL without opening a database connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _configure_url() -> dict[str, str]:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    return section


async def run_async_migrations() -> None:
    """Run migrations through SQLAlchemy's async engine."""
    connectable = async_engine_from_config(
        _configure_url(),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await connectable.dispose()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if sys.platform == "win32":
        # WHY: psycopg async explicitly rejects Python's Windows ProactorEventLoop.
        asyncio.run(
            run_async_migrations(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
