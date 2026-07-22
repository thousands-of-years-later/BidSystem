"""Security boundary tests for access tokens and refresh-token material."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from bid_system.platform.config import AuthSettings, JwtVerificationKeySettings
from bid_system.platform.security.authentication import (
    ACCESS_TOKEN_TYPE,
    AccessTokenIssuer,
    AccessTokenVerifier,
    BearerTokenParser,
    RefreshTokenDigest,
    RefreshTokenGenerator,
    TokenValidationError,
)

KEY_ID = "test-key-1"
ISSUER = "bid-system"
AUDIENCE = "bid-system-api"
NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def _key_pair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_pem, public_pem


def _settings(private_key: str, public_key: str) -> AuthSettings:
    return AuthSettings(
        enabled=True,
        algorithm="RS256",
        active_key_id=KEY_ID,
        signing_private_key=SecretStr(private_key),
        verification_keys=(
            JwtVerificationKeySettings(
                key_id=KEY_ID,
                public_key=SecretStr(public_key),
            ),
        ),
        issuer=ISSUER,
        audience=AUDIENCE,
        access_token_ttl_seconds=900,
        refresh_token_absolute_ttl_seconds=2_592_000,
        refresh_token_idle_ttl_seconds=604_800,
        refresh_cookie_secure=True,
        argon2_memory_cost_kib=19_456,
        argon2_time_cost=2,
        argon2_parallelism=1,
    )


def test_issues_and_verifies_typed_access_token() -> None:
    private_key, public_key = _key_pair()
    settings = _settings(private_key, public_key)

    token = AccessTokenIssuer(settings).issue(
        subject="user-1",
        tenant_id="tenant-1",
        session_id="session-1",
        token_id="token-1",
        issued_at=NOW,
    )
    claims = AccessTokenVerifier(settings).verify(token, verified_at=NOW)

    assert jwt.get_unverified_header(token) == {
        "alg": "RS256",
        "kid": KEY_ID,
        "typ": ACCESS_TOKEN_TYPE,
    }
    assert claims.subject == "user-1"
    assert claims.tenant_id == "tenant-1"
    assert claims.session_id == "session-1"
    assert claims.token_id == "token-1"
    assert claims.expires_at == NOW + timedelta(seconds=900)


@pytest.mark.parametrize("claim", ("sub", "tenant_id", "session_id", "jti"))
def test_rejects_missing_required_identity_claim(claim: str) -> None:
    private_key, public_key = _key_pair()
    settings = _settings(private_key, public_key)
    payload: dict[str, str | int] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-1",
        "tenant_id": "tenant-1",
        "session_id": "session-1",
        "jti": "token-1",
        "iat": int(NOW.timestamp()),
        "nbf": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=15)).timestamp()),
    }
    del payload[claim]
    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID, "typ": ACCESS_TOKEN_TYPE},
    )

    with pytest.raises(TokenValidationError, match="Access token is invalid"):
        AccessTokenVerifier(settings).verify(token, verified_at=NOW)


def test_rejects_expired_token_and_unknown_key_without_leaking_details() -> None:
    private_key, public_key = _key_pair()
    settings = _settings(private_key, public_key)
    expired = AccessTokenIssuer(settings).issue(
        subject="user-1",
        tenant_id="tenant-1",
        session_id="session-1",
        token_id="token-1",
        issued_at=NOW - timedelta(hours=1),
    )

    with pytest.raises(TokenValidationError, match="Access token is invalid") as expired_error:
        AccessTokenVerifier(settings).verify(expired, verified_at=NOW)
    assert "expired" not in str(expired_error.value).lower()

    unknown_key_token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "user-1",
            "tenant_id": "tenant-1",
            "session_id": "session-1",
            "jti": "token-1",
            "iat": int(NOW.timestamp()),
            "nbf": int(NOW.timestamp()),
            "exp": int((NOW + timedelta(minutes=15)).timestamp()),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "unknown-key", "typ": ACCESS_TOKEN_TYPE},
    )
    with pytest.raises(TokenValidationError, match="Access token is invalid"):
        AccessTokenVerifier(settings).verify(unknown_key_token, verified_at=NOW)


def test_refresh_tokens_are_url_safe_random_and_only_digest_is_stable() -> None:
    generator = RefreshTokenGenerator(random_bytes=lambda length: b"x" * length)

    token = generator.generate()

    assert token == "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg"
    assert RefreshTokenDigest.digest(token) == RefreshTokenDigest.digest(token)
    assert token not in RefreshTokenDigest.digest(token)


def test_parses_single_bearer_credential_case_insensitively() -> None:
    assert BearerTokenParser.parse("bearer token-value") == "token-value"


@pytest.mark.parametrize("header", (None, "", "Basic value", "Bearer", "Bearer one two"))
def test_rejects_missing_or_malformed_bearer_credential(header: str | None) -> None:
    with pytest.raises(TokenValidationError, match="Access token is invalid"):
        BearerTokenParser.parse(header)
