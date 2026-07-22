"""Minimal local account and tenant membership behavior."""

from bid_system.modules.identity.domain.account import AccountStatus, LocalAccount
from bid_system.modules.identity.domain.membership import MembershipStatus, TenantMembership


def test_registers_normalized_active_local_account() -> None:
    account = LocalAccount.register(
        user_id="user-1",
        login_identifier=" User@Example.test ",
        password_hash="$argon2id$encoded",
    )

    assert account.login_identifier == "user@example.test"
    assert account.status is AccountStatus.ACTIVE
    assert account.password_version == 1


def test_disabled_account_cannot_authenticate() -> None:
    account = LocalAccount.register(
        user_id="user-1",
        login_identifier="user@example.test",
        password_hash="$argon2id$encoded",
    ).disable()

    assert account.can_authenticate is False


def test_active_membership_exposes_only_its_tenant_grants() -> None:
    membership = TenantMembership.create(
        membership_id="membership-1",
        user_id="user-1",
        tenant_id="tenant-1",
        roles=frozenset({"reviewer"}),
        permissions=frozenset({"documents.read"}),
    )

    assert membership.status is MembershipStatus.ACTIVE
    assert membership.permissions == frozenset({"documents.read"})
