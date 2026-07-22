"""Local login use-case behavior."""

from datetime import UTC, datetime, timedelta

import pytest

from bid_system.modules.identity.application.authenticate import (
    AuthenticateLocalAccountCommand,
    AuthenticateLocalAccountHandler,
)
from bid_system.modules.identity.application.ports import PasswordCheckResult
from bid_system.modules.identity.domain.account import LocalAccount
from bid_system.modules.identity.domain.membership import TenantMembership
from bid_system.modules.identity.domain.session import RefreshSession
from bid_system.shared.contracts.errors import AuthenticationError

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


class PasswordVerifierStub:
    def __init__(self, *, valid: bool) -> None:
        self.valid = valid

    def verify(self, password: str, encoded_hash: str | None) -> PasswordCheckResult:
        del password, encoded_hash
        return PasswordCheckResult(valid=self.valid, updated_hash=None)


class AuthenticationStoreStub:
    def __init__(self) -> None:
        self.account = LocalAccount.register(
            user_id="user-1",
            login_identifier="user@example.test",
            password_hash="$argon2id$encoded",
        )
        self.membership = TenantMembership.create(
            membership_id="membership-1",
            user_id="user-1",
            tenant_id="tenant-1",
            roles=frozenset({"reviewer"}),
            permissions=frozenset({"documents.read"}),
        )
        self.created: RefreshSession | None = None

    async def get_account_by_login(self, login_identifier: str) -> LocalAccount | None:
        return self.account if login_identifier == self.account.login_identifier else None

    async def get_membership(self, user_id: str, tenant_id: str) -> TenantMembership | None:
        return self.membership if (user_id, tenant_id) == ("user-1", "tenant-1") else None

    async def update_password_hash(self, account: LocalAccount) -> None:
        self.account = account

    async def add_refresh_session(self, session: RefreshSession) -> None:
        self.created = session


def _command() -> AuthenticateLocalAccountCommand:
    return AuthenticateLocalAccountCommand(
        login_identifier=" User@Example.test ",
        password="safe-password",
        tenant_id="tenant-1",
        session_id="session-1",
        family_id="family-1",
        refresh_token_digest="a" * 64,
        authenticated_at=NOW,
        idle_ttl=timedelta(days=7),
        absolute_ttl=timedelta(days=30),
    )


@pytest.mark.asyncio
async def test_authenticates_and_creates_tenant_bound_refresh_session() -> None:
    store = AuthenticationStoreStub()

    result = await AuthenticateLocalAccountHandler(
        store=store,
        password_verifier=PasswordVerifierStub(valid=True),
    ).handle(_command())

    assert result.user_id == "user-1"
    assert store.created is not None
    assert store.created.tenant_id == "tenant-1"


@pytest.mark.asyncio
async def test_invalid_password_returns_non_diagnostic_authentication_error() -> None:
    with pytest.raises(AuthenticationError):
        await AuthenticateLocalAccountHandler(
            store=AuthenticationStoreStub(),
            password_verifier=PasswordVerifierStub(valid=False),
        ).handle(_command())
