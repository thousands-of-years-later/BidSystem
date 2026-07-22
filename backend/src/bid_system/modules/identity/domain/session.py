"""Refresh-session family rules independent of JWT and persistence libraries."""

import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

INVALID_REFRESH_SESSION_MESSAGE = "Refresh session is invalid"


class InvalidRefreshSessionError(ValueError):
    """A refresh credential cannot be used without revealing the exact reason."""

    def __init__(self) -> None:
        super().__init__(INVALID_REFRESH_SESSION_MESSAGE)


class RefreshTokenReplayError(InvalidRefreshSessionError):
    """A consumed token was reused, requiring revocation of its entire family."""

    def __init__(self, family_id: str) -> None:
        super().__init__()
        self.family_id = family_id


@dataclass(frozen=True)
class RefreshSession:
    """One single-use refresh credential in a revocable session family."""

    session_id: str
    family_id: str
    user_id: str
    tenant_id: str
    token_digest: str
    issued_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        identifiers = (
            self.session_id,
            self.family_id,
            self.user_id,
            self.tenant_id,
            self.token_digest,
        )
        if any(not value.strip() for value in identifiers):
            raise ValueError("Refresh-session identifiers must not be blank")
        timestamps = (self.issued_at, self.idle_expires_at, self.absolute_expires_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            raise ValueError("Refresh-session timestamps must be timezone-aware")
        if self.idle_expires_at > self.absolute_expires_at:
            raise ValueError("Idle expiry must not exceed absolute expiry")

    @classmethod
    def issue(
        cls,
        *,
        session_id: str,
        family_id: str,
        user_id: str,
        tenant_id: str,
        token_digest: str,
        issued_at: datetime,
        idle_ttl: timedelta,
        absolute_ttl: timedelta,
    ) -> "RefreshSession":
        _validate_positive_ttl(idle_ttl)
        _validate_positive_ttl(absolute_ttl)
        absolute_expires_at = issued_at + absolute_ttl
        return cls(
            session_id=session_id,
            family_id=family_id,
            user_id=user_id,
            tenant_id=tenant_id,
            token_digest=token_digest,
            issued_at=issued_at,
            idle_expires_at=min(issued_at + idle_ttl, absolute_expires_at),
            absolute_expires_at=absolute_expires_at,
        )

    def rotate(
        self,
        *,
        presented_digest: str,
        replacement_session_id: str,
        replacement_token_digest: str,
        rotated_at: datetime,
        idle_ttl: timedelta,
    ) -> tuple["RefreshSession", "RefreshSession"]:
        """Consume this credential and create its sole valid replacement."""
        _validate_positive_ttl(idle_ttl)
        if not secrets.compare_digest(self.token_digest, presented_digest):
            raise InvalidRefreshSessionError
        if self.consumed_at is not None:
            # WHY: exact reuse proves that one party holds a copied credential.
            raise RefreshTokenReplayError(self.family_id)
        if (
            self.revoked_at is not None
            or rotated_at >= self.idle_expires_at
            or rotated_at >= self.absolute_expires_at
        ):
            raise InvalidRefreshSessionError
        consumed = replace(self, consumed_at=rotated_at)
        replacement = RefreshSession(
            session_id=replacement_session_id,
            family_id=self.family_id,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            token_digest=replacement_token_digest,
            issued_at=rotated_at,
            idle_expires_at=min(rotated_at + idle_ttl, self.absolute_expires_at),
            absolute_expires_at=self.absolute_expires_at,
        )
        return consumed, replacement

    def revoke(self, *, revoked_at: datetime) -> "RefreshSession":
        """Return an idempotently revoked form of this session."""
        if self.revoked_at is not None:
            return self
        return replace(self, revoked_at=revoked_at)

    def is_active(self, *, checked_at: datetime) -> bool:
        """Return whether this session may back an access-token principal now."""
        return (
            self.consumed_at is None
            and self.revoked_at is None
            and checked_at < self.idle_expires_at
            and checked_at < self.absolute_expires_at
        )


def _validate_positive_ttl(value: timedelta) -> None:
    if value <= timedelta(0):
        raise ValueError("Refresh-session TTL must be positive")
