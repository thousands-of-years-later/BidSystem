"""PostgreSQL integration fixtures with mandatory test-database isolation."""

import asyncio
import os
import platform
import selectors
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
APPLICATION_DATABASE_URL_ENV = "DATABASE_URL"
TEST_DATABASE_SUFFIX = "_test"


type LoopFactory = Callable[[], asyncio.AbstractEventLoop]


def _selector_event_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> dict[str, LoopFactory]:
    """Select the event loop implementation required by psycopg on Windows."""
    del config, item
    if platform.system() == "Windows":
        return {"selector": _selector_event_loop}
    return {"default": asyncio.new_event_loop}


def _test_database_url() -> str:
    test_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")
    application_url = os.environ.get(APPLICATION_DATABASE_URL_ENV)
    if application_url and make_url(test_url) == make_url(application_url):
        raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL")
    database_name = make_url(test_url).database or ""
    if not database_name.endswith(TEST_DATABASE_SUFFIX):
        raise RuntimeError(f"Test database name must end with {TEST_DATABASE_SUFFIX}")
    return test_url


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_test_database_url(), pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Rollback every test even when application code commits savepoints."""
    async with db_engine.connect() as connection:
        outer_transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()
