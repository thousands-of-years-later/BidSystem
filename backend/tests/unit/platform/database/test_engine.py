"""Unit tests for the async database engine resource."""

from unittest.mock import Mock, patch

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from bid_system.platform.config import DatabaseSettings
from bid_system.platform.database.engine import DatabaseResource


def test_database_resource_builds_configured_async_engine_and_session_factory() -> None:
    engine = Mock(spec=AsyncEngine)
    settings = DatabaseSettings(
        url=SecretStr("postgresql+psycopg://user:secret@localhost/database"),
        pool_size=7,
        max_overflow=4,
        pool_timeout_seconds=12.5,
    )

    with patch(
        "bid_system.platform.database.engine.create_async_engine", return_value=engine
    ) as create_engine:
        resource = DatabaseResource(settings)

    create_engine.assert_called_once_with(
        "postgresql+psycopg://user:secret@localhost/database",
        pool_size=7,
        max_overflow=4,
        pool_timeout=12.5,
        pool_pre_ping=True,
    )
    assert resource.engine is engine
    assert resource.session_factory.kw["bind"] is engine
    assert resource.transaction().session_factory is resource.session_factory
