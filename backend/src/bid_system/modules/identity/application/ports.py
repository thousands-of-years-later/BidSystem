"""Persistence capabilities required by identity queries."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from bid_system.modules.identity.domain.access import IdentityRole
from bid_system.modules.identity.domain.account import LocalAccount
from bid_system.modules.identity.domain.membership import TenantMembership
from bid_system.modules.identity.domain.session import RefreshSession


class IdentityReader(Protocol):
    """Read current identity facts without exposing ORM or database sessions."""

    async def get_account(self, user_id: str) -> LocalAccount | None: ...

    async def get_membership(
        self,
        user_id: str,
        tenant_id: str,
    ) -> TenantMembership | None: ...

    async def get_session(self, session_id: str) -> RefreshSession | None: ...


@dataclass(frozen=True)
class PasswordCheckResult:
    """Password comparison result independent of a hashing library."""

    valid: bool
    updated_hash: str | None


class PasswordVerifier(Protocol):
    """Adaptive password verification port with missing-account timing equalization."""

    def verify(self, password: str, encoded_hash: str | None) -> PasswordCheckResult: ...


class PasswordEncoder(Protocol):
    """One-way password encoding used only while creating local accounts."""

    def hash(self, password: str) -> str: ...


@dataclass(frozen=True)
class RegistrationRecord:
    """Complete identity aggregate persisted atomically during account creation."""

    account: LocalAccount
    membership: TenantMembership
    role: IdentityRole


class RegistrationStore(Protocol):
    """Identity registration writes and serialized manager bootstrap lookup."""

    async def manager_exists_for_update(self, tenant_id: str) -> bool: ...

    async def get_membership(
        self,
        user_id: str,
        tenant_id: str,
    ) -> TenantMembership | None: ...

    async def add_registration(self, record: RegistrationRecord) -> None: ...


class AuthenticationStore(Protocol):
    """Identity writes needed by local login inside the caller's transaction."""

    async def get_account_by_login(self, login_identifier: str) -> LocalAccount | None: ...

    async def get_membership(
        self,
        user_id: str,
        tenant_id: str,
    ) -> TenantMembership | None: ...

    async def update_password_hash(self, account: LocalAccount) -> None: ...

    async def add_refresh_session(self, session: RefreshSession) -> None: ...


class RefreshRotationStatus(StrEnum):
    """Transaction-safe refresh outcome returned without forcing rollback on replay."""

    ROTATED = "rotated"
    INVALID = "invalid"
    REPLAY_REVOKED = "replay_revoked"


@dataclass(frozen=True)
class RefreshRotationResult:
    """Refresh outcome whose replay form must be committed before returning 401."""

    status: RefreshRotationStatus
    session: RefreshSession | None


class RefreshSessionStore(Protocol):
    """Atomic refresh rotation and revocation persistence port."""

    async def rotate_refresh_session(
        self,
        *,
        presented_digest: str,
        replacement_session_id: str,
        replacement_digest: str,
        rotated_at: datetime,
        idle_ttl: timedelta,
    ) -> RefreshRotationResult: ...

    async def revoke_refresh_family_by_digest(
        self,
        *,
        token_digest: str,
        revoked_at: datetime,
    ) -> bool: ...


class IdentityAuthenticationRepository(
    IdentityReader,
    AuthenticationStore,
    RefreshSessionStore,
    RegistrationStore,
    Protocol,
):
    """Combined identity capability assembled only at the bootstrap boundary."""
