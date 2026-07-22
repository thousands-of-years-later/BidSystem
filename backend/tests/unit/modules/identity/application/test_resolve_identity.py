"""Current identity resolution use-case tests."""

from datetime import UTC, datetime, timedelta

import pytest

from bid_system.modules.identity.application.resolve_identity import (
    ResolveIdentityHandler,
    ResolveIdentityQuery,
)
from bid_system.modules.identity.domain.account import LocalAccount
from bid_system.modules.identity.domain.membership import TenantMembership
from bid_system.modules.identity.domain.session import RefreshSession
from bid_system.shared.contracts.errors import AuthenticationError

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


class IdentityReaderStub:
    def __init__(self, *, disabled_account: bool = False) -> None:
        account = LocalAccount.register(
            user_id="user-1",
            login_identifier="user@example.test",
            password_hash="$argon2id$encoded",
        )
        self.account = account.disable() if disabled_account else account
        self.membership = TenantMembership.create(
            membership_id="membership-1",
            user_id="user-1",
            tenant_id="tenant-1",
            roles=frozenset({"reviewer"}),
            permissions=frozenset({"documents.read"}),
        )
        self.session = RefreshSession.issue(
            session_id="session-1",
            family_id="family-1",
            user_id="user-1",
            tenant_id="tenant-1",
            token_digest="digest-1",
            issued_at=NOW,
            idle_ttl=timedelta(days=7),
            absolute_ttl=timedelta(days=30),
        )

    async def get_account(self, user_id: str) -> LocalAccount | None:
        return self.account if user_id == self.account.user_id else None

    async def get_membership(self, user_id: str, tenant_id: str) -> TenantMembership | None:
        if user_id == self.membership.user_id and tenant_id == self.membership.tenant_id:
            return self.membership
        return None

    async def get_session(self, session_id: str) -> RefreshSession | None:
        return self.session if session_id == self.session.session_id else None


@pytest.mark.asyncio
async def test_resolves_current_identity_from_current_authoritative_state() -> None:
    result = await ResolveIdentityHandler(IdentityReaderStub()).handle(
        ResolveIdentityQuery(
            user_id="user-1",
            tenant_id="tenant-1",
            session_id="session-1",
            resolved_at=NOW + timedelta(minutes=1),
        )
    )

    assert result.user_id == "user-1"
    assert result.roles == frozenset({"reviewer"})
    assert result.permissions == frozenset({"documents.read"})


@pytest.mark.asyncio
async def test_disabled_account_is_rejected_even_with_valid_token_claims() -> None:
    with pytest.raises(AuthenticationError):
        await ResolveIdentityHandler(IdentityReaderStub(disabled_account=True)).handle(
            ResolveIdentityQuery(
                user_id="user-1",
                tenant_id="tenant-1",
                session_id="session-1",
                resolved_at=NOW + timedelta(minutes=1),
            )
        )
