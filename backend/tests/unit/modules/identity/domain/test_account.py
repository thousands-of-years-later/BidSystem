"""Minimal local account, registration, and tenant membership behavior."""

import pytest

from bid_system.modules.identity.domain.access import (
    IdentityRole,
    PermissionCode,
    RegistrationCredentials,
    permissions_for_role,
)
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


def test_registration_credentials_normalize_and_validate_username_and_password() -> None:
    credentials = RegistrationCredentials.create(
        username=" Manager_01 ",
        password="secure123",
    )

    assert credentials.username == "manager_01"


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("ab", "secure123"),
        ("bad-name", "secure123"),
        ("valid_name", "short"),
        ("valid_name", "onlyletters"),
        ("valid_name", "12345678"),
        ("same123", "same123"),
    ],
)
def test_registration_credentials_reject_common_invalid_inputs(
    username: str,
    password: str,
) -> None:
    with pytest.raises(ValueError):
        RegistrationCredentials.create(username=username, password=password)


def test_role_permission_matrix_restricts_employee_mutations() -> None:
    assert permissions_for_role(IdentityRole.MANAGER) == frozenset(PermissionCode)
    assert permissions_for_role(IdentityRole.EMPLOYEE) == frozenset()
