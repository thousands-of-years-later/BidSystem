"""Deterministic authentication cryptography without account-domain decisions."""

import base64
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

from bid_system.platform.config import AuthSettings

ACCESS_TOKEN_TYPE = "at+jwt"
SUPPORTED_JWT_ALGORITHM = "RS256"
REFRESH_TOKEN_ENTROPY_BYTES = 32
MAX_ACCESS_TOKEN_LENGTH = 8_192
MAX_PASSWORD_LENGTH_BYTES = 1_024
INVALID_ACCESS_TOKEN_MESSAGE = "Access token is invalid"


class TokenValidationError(ValueError):
    """A credential is malformed, untrusted, or outside its validity window."""

    def __init__(self) -> None:
        # WHY: callers and logs must not reveal which token property aided an attacker.
        super().__init__(INVALID_ACCESS_TOKEN_MESSAGE)


class BearerTokenParser:
    """Extract exactly one bearer credential from an HTTP Authorization header."""

    @staticmethod
    def parse(authorization_header: str | None) -> str:
        if authorization_header is None:
            raise TokenValidationError
        parts = authorization_header.split()
        if len(parts) != 2 or parts[0].casefold() != "bearer" or not parts[1]:
            raise TokenValidationError
        return parts[1]


@dataclass(frozen=True)
class AccessTokenClaims:
    """Trusted access-token claims after every cryptographic and structural check."""

    issuer: str
    audience: str
    subject: str
    tenant_id: str
    session_id: str
    token_id: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Current account and tenant grants resolved from trusted identity state."""

    user_id: str
    tenant_id: str
    session_id: str
    roles: frozenset[str]
    permissions: frozenset[str]
    active: bool


class AccessTokenIssuer:
    """Issue access tokens with one configured private key and explicit token type."""

    def __init__(self, settings: AuthSettings) -> None:
        self._settings = settings
        if (
            not settings.enabled
            or settings.algorithm != SUPPORTED_JWT_ALGORITHM
            or settings.active_key_id is None
            or settings.signing_private_key is None
            or settings.issuer is None
            or settings.audience is None
        ):
            raise ValueError("Access-token issuer configuration is incomplete")

    def issue(
        self,
        *,
        subject: str,
        tenant_id: str,
        session_id: str,
        token_id: str,
        issued_at: datetime,
    ) -> str:
        """Create one tenant-bound access token with a fixed lifetime."""
        values = (subject, tenant_id, session_id, token_id)
        if any(not value.strip() for value in values):
            raise ValueError("Access-token identity values must not be blank")
        normalized_issued_at = _require_aware_utc(issued_at)
        expires_at = normalized_issued_at + timedelta(
            seconds=self._settings.access_token_ttl_seconds
        )
        payload: dict[str, str | int] = {
            "iss": _required_value(self._settings.issuer),
            "aud": _required_value(self._settings.audience),
            "sub": subject,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "jti": token_id,
            "iat": int(normalized_issued_at.timestamp()),
            "nbf": int(normalized_issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(
            payload,
            _required_secret(self._settings),
            algorithm=SUPPORTED_JWT_ALGORITHM,
            headers={"kid": self._settings.active_key_id, "typ": ACCESS_TOKEN_TYPE},
        )


class AccessTokenVerifier:
    """Verify access tokens against an explicit public-key ring and claim contract."""

    def __init__(self, settings: AuthSettings) -> None:
        self._settings = settings
        if (
            not settings.enabled
            or settings.algorithm != SUPPORTED_JWT_ALGORITHM
            or settings.issuer is None
            or settings.audience is None
            or not settings.verification_keys
        ):
            raise ValueError("Access-token verifier configuration is incomplete")
        self._verification_keys = {
            key.key_id: key.public_key.get_secret_value() for key in settings.verification_keys
        }

    def verify(self, token: str, *, verified_at: datetime) -> AccessTokenClaims:
        """Return trusted claims or one intentionally non-diagnostic error."""
        if not token or len(token) > MAX_ACCESS_TOKEN_LENGTH:
            raise TokenValidationError
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            token_type = header.get("typ")
            key_id = header.get("kid")
            if (
                algorithm != SUPPORTED_JWT_ALGORITHM
                or token_type != ACCESS_TOKEN_TYPE
                or not isinstance(key_id, str)
                or key_id not in self._verification_keys
            ):
                raise TokenValidationError
            decoded = jwt.decode(
                token,
                self._verification_keys[key_id],
                algorithms=[SUPPORTED_JWT_ALGORITHM],
                audience=_required_value(self._settings.audience),
                issuer=_required_value(self._settings.issuer),
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "tenant_id",
                        "session_id",
                        "jti",
                        "iat",
                        "nbf",
                        "exp",
                    ],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
            return self._validated_claims(decoded, verified_at=verified_at)
        except TokenValidationError:
            raise
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise TokenValidationError from error

    def _validated_claims(
        self,
        decoded: dict[str, object],
        *,
        verified_at: datetime,
    ) -> AccessTokenClaims:
        string_claim_names = ("iss", "aud", "sub", "tenant_id", "session_id", "jti")
        string_claims: dict[str, str] = {}
        for name in string_claim_names:
            value = decoded.get(name)
            if not isinstance(value, str) or not value.strip():
                raise TokenValidationError
            string_claims[name] = value
        time_claims: dict[str, int] = {}
        for name in ("iat", "nbf", "exp"):
            value = decoded.get(name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TokenValidationError
            time_claims[name] = value
        now_timestamp = int(_require_aware_utc(verified_at).timestamp())
        if (
            time_claims["iat"] > now_timestamp
            or time_claims["nbf"] > now_timestamp
            or time_claims["exp"] <= now_timestamp
        ):
            raise TokenValidationError
        return AccessTokenClaims(
            issuer=string_claims["iss"],
            audience=string_claims["aud"],
            subject=string_claims["sub"],
            tenant_id=string_claims["tenant_id"],
            session_id=string_claims["session_id"],
            token_id=string_claims["jti"],
            issued_at=datetime.fromtimestamp(time_claims["iat"], tz=UTC),
            not_before=datetime.fromtimestamp(time_claims["nbf"], tz=UTC),
            expires_at=datetime.fromtimestamp(time_claims["exp"], tz=UTC),
        )


class RefreshTokenGenerator:
    """Generate opaque refresh-token material with 256 bits of entropy."""

    def __init__(self, *, random_bytes: Callable[[int], bytes] = secrets.token_bytes) -> None:
        self._random_bytes = random_bytes

    def generate(self) -> str:
        raw_token = self._random_bytes(REFRESH_TOKEN_ENTROPY_BYTES)
        if len(raw_token) != REFRESH_TOKEN_ENTROPY_BYTES:
            raise ValueError("Refresh-token entropy source returned the wrong byte count")
        return base64.urlsafe_b64encode(raw_token).rstrip(b"=").decode("ascii")


class RefreshTokenDigest:
    """Produce the database-safe lookup digest of a high-entropy refresh token."""

    @staticmethod
    def digest(token: str) -> str:
        if not token:
            raise ValueError("Refresh token must not be blank")
        return hashlib.sha256(token.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class PasswordVerificationResult:
    """Password comparison result and optional upgraded encoded hash."""

    valid: bool
    updated_hash: str | None


class PasswordHasher:
    """Argon2id password hashing with explicit, upgradeable work factors."""

    def __init__(self, *, memory_cost_kib: int, time_cost: int, parallelism: int) -> None:
        self._password_hash = PasswordHash(
            (
                Argon2Hasher(
                    memory_cost=memory_cost_kib,
                    time_cost=time_cost,
                    parallelism=parallelism,
                ),
            )
        )

    def hash_password(self, password: str) -> str:
        _validate_password(password)
        return self._password_hash.hash(password)

    def verify_and_update(self, password: str, encoded_hash: str) -> PasswordVerificationResult:
        _validate_password(password)
        try:
            valid, updated_hash = self._password_hash.verify_and_update(password, encoded_hash)
        except UnknownHashError:
            return PasswordVerificationResult(valid=False, updated_hash=None)
        return PasswordVerificationResult(valid=valid, updated_hash=updated_hash)


def _required_value(value: str | None) -> str:
    if value is None:
        raise ValueError("Authentication configuration is incomplete")
    return value


def _required_secret(settings: AuthSettings) -> str:
    if settings.signing_private_key is None:
        raise ValueError("Authentication configuration is incomplete")
    return settings.signing_private_key.get_secret_value()


def _require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Authentication timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _validate_password(password: str) -> None:
    password_length = len(password.encode("utf-8"))
    if password_length == 0 or password_length > MAX_PASSWORD_LENGTH_BYTES:
        raise ValueError("Password length is outside the supported boundary")
