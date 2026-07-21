"""Tests for standalone session cleanup."""

from unittest.mock import AsyncMock, Mock

import pytest

from bid_system.platform.database.session import session_scope


@pytest.mark.asyncio
async def test_session_scope_closes_after_success() -> None:
    session = Mock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()

    async with session_scope(Mock(return_value=session)) as yielded:
        assert yielded is session

    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_session_scope_rolls_back_and_closes_after_error() -> None:
    session = Mock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()

    with pytest.raises(RuntimeError, match="failed"):
        async with session_scope(Mock(return_value=session)):
            raise RuntimeError("failed")

    session.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()
