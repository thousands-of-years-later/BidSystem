"""Password hashing policy tests."""

from bid_system.platform.security.authentication import PasswordHasher


def test_hashes_and_verifies_unicode_password_with_argon2id() -> None:
    hasher = PasswordHasher(memory_cost_kib=19_456, time_cost=2, parallelism=1)

    encoded = hasher.hash_password("正确的密码-🔐")
    result = hasher.verify_and_update("正确的密码-🔐", encoded)

    assert encoded.startswith("$argon2id$")
    assert result.valid is True
    assert result.updated_hash is None
    assert hasher.verify_and_update("错误密码", encoded).valid is False


def test_rehashes_valid_password_when_argon2_policy_is_upgraded() -> None:
    old_hasher = PasswordHasher(memory_cost_kib=19_456, time_cost=2, parallelism=1)
    encoded = old_hasher.hash_password("safe-password")
    upgraded_hasher = PasswordHasher(memory_cost_kib=19_456, time_cost=3, parallelism=1)

    result = upgraded_hasher.verify_and_update("safe-password", encoded)

    assert result.valid is True
    assert result.updated_hash is not None
    assert "t=3" in result.updated_hash


def test_malformed_hash_is_rejected_without_exception() -> None:
    hasher = PasswordHasher(memory_cost_kib=19_456, time_cost=2, parallelism=1)

    result = hasher.verify_and_update("safe-password", "not-a-password-hash")

    assert result.valid is False
    assert result.updated_hash is None
