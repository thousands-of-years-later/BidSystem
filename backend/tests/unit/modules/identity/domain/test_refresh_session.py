"""Core refresh-session rotation behavior."""

from datetime import UTC, datetime, timedelta

import pytest

from bid_system.modules.identity.domain.session import (
    InvalidRefreshSessionError,
    RefreshSession,
    RefreshTokenReplayError,
)

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def _session() -> RefreshSession:
    return RefreshSession.issue(
        session_id="session-1",
        family_id="family-1",
        user_id="user-1",
        tenant_id="tenant-1",
        token_digest="digest-1",
        issued_at=NOW,
        idle_ttl=timedelta(days=7),
        absolute_ttl=timedelta(days=30),
    )


def test_rotates_once_and_preserves_family_expiry() -> None:
    consumed, replacement = _session().rotate(
        presented_digest="digest-1",
        replacement_session_id="session-2",
        replacement_token_digest="digest-2",
        rotated_at=NOW + timedelta(days=1),
        idle_ttl=timedelta(days=7),
    )

    assert consumed.consumed_at == NOW + timedelta(days=1)
    assert replacement.family_id == "family-1"
    assert replacement.absolute_expires_at == NOW + timedelta(days=30)


def test_consumed_token_reuse_signals_family_replay() -> None:
    consumed, _ = _session().rotate(
        presented_digest="digest-1",
        replacement_session_id="session-2",
        replacement_token_digest="digest-2",
        rotated_at=NOW + timedelta(minutes=1),
        idle_ttl=timedelta(days=7),
    )

    with pytest.raises(RefreshTokenReplayError) as error:
        consumed.rotate(
            presented_digest="digest-1",
            replacement_session_id="session-3",
            replacement_token_digest="digest-3",
            rotated_at=NOW + timedelta(minutes=2),
            idle_ttl=timedelta(days=7),
        )

    assert error.value.family_id == "family-1"


def test_expired_session_is_rejected() -> None:
    with pytest.raises(InvalidRefreshSessionError, match="Refresh session is invalid"):
        _session().rotate(
            presented_digest="digest-1",
            replacement_session_id="session-2",
            replacement_token_digest="digest-2",
            rotated_at=NOW + timedelta(days=8),
            idle_ttl=timedelta(days=7),
        )
