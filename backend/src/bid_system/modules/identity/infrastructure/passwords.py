"""Argon2 password-verification adapter for identity application ports."""

from bid_system.modules.identity.application.ports import PasswordCheckResult
from bid_system.platform.security.authentication import PasswordHasher


class Argon2PasswordVerifier:
    """Verify real hashes and spend equivalent work for unknown login identifiers."""

    def __init__(self, password_hasher: PasswordHasher) -> None:
        self._password_hasher = password_hasher

    def verify(self, password: str, encoded_hash: str | None) -> PasswordCheckResult:
        if encoded_hash is None:
            # WHY: hashing an unknown account password avoids a cheap identifier oracle.
            self._password_hasher.hash_password(password)
            return PasswordCheckResult(valid=False, updated_hash=None)
        result = self._password_hasher.verify_and_update(password, encoded_hash)
        return PasswordCheckResult(valid=result.valid, updated_hash=result.updated_hash)
