"""Tests for request-scoped database transaction injection."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bid_system.bootstrap.container import ApplicationContainer
from bid_system.entrypoints.api.dependencies import get_database_transaction
from bid_system.platform.config import AppSettings
from bid_system.platform.database.transaction import AsyncTransactionManager


class FakeDatabaseResource:
    def __init__(self, transaction: AsyncTransactionManager) -> None:
        self._transaction = transaction

    async def probe(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def transaction(self) -> AsyncTransactionManager:
        return self._transaction


def _request(transaction: AsyncTransactionManager) -> Request:
    settings = AppSettings(
        APP_ENV="test",
        DATABASE_URL="postgresql+psycopg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="access",
        MINIO_SECRET_KEY="secret",
        MINIO_BUCKET="bucket",
    )
    container = ApplicationContainer(settings)
    container.database = FakeDatabaseResource(transaction)
    app = FastAPI()
    app.state.container = container
    return Request({"type": "http", "app": app, "headers": []})


@pytest.mark.asyncio
async def test_request_dependency_commits_and_closes_session() -> None:
    session = Mock()
    session.begin = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    transaction = AsyncTransactionManager(Mock(return_value=session))
    dependency = get_database_transaction(_request(transaction))

    yielded = await anext(dependency)
    assert yielded is transaction
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)

    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_request_dependency_rolls_back_and_closes_on_error() -> None:
    session = Mock()
    session.begin = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    transaction = AsyncTransactionManager(Mock(return_value=session))
    dependency = get_database_transaction(_request(transaction))

    await anext(dependency)
    with pytest.raises(ValueError, match="request failed"):
        await dependency.athrow(ValueError("request failed"))

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()
