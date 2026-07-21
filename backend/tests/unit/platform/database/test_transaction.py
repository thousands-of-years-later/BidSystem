"""Tests for deterministic transaction completion and cleanup."""

from unittest.mock import AsyncMock, Mock

import pytest

from bid_system.platform.database.transaction import AsyncTransactionManager


def _factory() -> tuple[Mock, Mock]:
    session = Mock()
    session.begin = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory = Mock(return_value=session)
    return factory, session


@pytest.mark.asyncio
async def test_transaction_commits_and_closes_on_success() -> None:
    factory, session = _factory()

    async with AsyncTransactionManager(factory) as transaction:
        assert transaction.session is session

    session.begin.assert_awaited_once_with()
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_transaction_rolls_back_and_closes_on_failure() -> None:
    factory, session = _factory()

    with pytest.raises(ValueError, match="invalid"):
        async with AsyncTransactionManager(factory):
            raise ValueError("invalid")

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_commit_failure_is_rolled_back_before_close() -> None:
    factory, session = _factory()
    session.commit.side_effect = RuntimeError("commit failed")

    with pytest.raises(RuntimeError, match="commit failed"):
        async with AsyncTransactionManager(factory):
            pass

    session.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()
