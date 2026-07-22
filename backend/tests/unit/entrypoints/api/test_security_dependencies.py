"""HTTP current-principal resolution tests."""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from bid_system.entrypoints.api.dependencies import resolve_current_principal
from bid_system.modules.identity.domain.account import LocalAccount
from bid_system.modules.identity.domain.membership import TenantMembership
from bid_system.modules.identity.domain.session import RefreshSession
from bid_system.platform.config import AuthSettings, JwtVerificationKeySettings
from bid_system.platform.security.authentication import AccessTokenIssuer

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


class IdentityReaderStub:
    account = LocalAccount.register(
        user_id="user-1",
        login_identifier="user@example.test",
        password_hash="$argon2id$encoded",
    )
    membership = TenantMembership.create(
        membership_id="membership-1",
        user_id="user-1",
        tenant_id="tenant-1",
        roles=frozenset({"reviewer"}),
        permissions=frozenset({"documents.read"}),
    )
    session = RefreshSession.issue(
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
        return self.account if user_id == "user-1" else None

    async def get_membership(self, user_id: str, tenant_id: str) -> TenantMembership | None:
        return self.membership if (user_id, tenant_id) == ("user-1", "tenant-1") else None

    async def get_session(self, session_id: str) -> RefreshSession | None:
        return self.session if session_id == "session-1" else None


def _settings() -> AuthSettings:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return AuthSettings(
        enabled=True,
        algorithm="RS256",
        active_key_id="key-1",
        signing_private_key=SecretStr(private_pem),
        verification_keys=(
            JwtVerificationKeySettings(key_id="key-1", public_key=SecretStr(public_pem)),
        ),
        issuer="bid-system",
        audience="bid-system-api",
        access_token_ttl_seconds=900,
        refresh_token_absolute_ttl_seconds=2_592_000,
        refresh_token_idle_ttl_seconds=604_800,
        refresh_cookie_secure=True,
        argon2_memory_cost_kib=19_456,
        argon2_time_cost=2,
        argon2_parallelism=1,
    )


@pytest.mark.asyncio
async def test_resolves_bearer_claims_to_current_authoritative_principal() -> None:
    settings = _settings()
    token = AccessTokenIssuer(settings).issue(
        subject="user-1",
        tenant_id="tenant-1",
        session_id="session-1",
        token_id="token-1",
        issued_at=NOW,
    )

    principal = await resolve_current_principal(
        authorization_header=f"Bearer {token}",
        auth_settings=settings,
        identity_reader=IdentityReaderStub(),
        resolved_at=NOW + timedelta(minutes=1),
    )

    assert principal.user_id == "user-1"
    assert principal.permissions == frozenset({"documents.read"})
