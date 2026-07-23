"""Manager-created account and bootstrap-manager use-case tests."""

import pytest

from bid_system.modules.identity.application.ports import RegistrationRecord
from bid_system.modules.identity.application.register import (
    BootstrapManagerCommand,
    BootstrapManagerHandler,
    RegisterLocalAccountCommand,
    RegisterLocalAccountHandler,
)
from bid_system.modules.identity.domain.access import IdentityRole
from bid_system.modules.identity.domain.membership import TenantMembership
from bid_system.shared.contracts.errors import PermissionDeniedError


class PasswordEncoderStub:
    def hash(self, password: str) -> str:
        return f"hash:{password}"


class RegistrationStoreStub:
    def __init__(
        self,
        *,
        manager_exists: bool = False,
        actor_role: IdentityRole = IdentityRole.MANAGER,
    ) -> None:
        self.manager_exists = manager_exists
        self.actor_role = actor_role
        self.records: list[RegistrationRecord] = []

    async def manager_exists_for_update(self, tenant_id: str) -> bool:
        assert tenant_id == "tenant-default"
        return self.manager_exists

    async def get_membership(
        self,
        user_id: str,
        tenant_id: str,
    ) -> TenantMembership | None:
        if user_id != "actor-1" or tenant_id != "tenant-default":
            return None
        return TenantMembership.create(
            membership_id="actor-membership-1",
            user_id=user_id,
            tenant_id=tenant_id,
            roles=frozenset({self.actor_role.value}),
            permissions=frozenset(),
        )

    async def add_registration(self, record: RegistrationRecord) -> None:
        self.records.append(record)
        if record.role is IdentityRole.MANAGER:
            self.manager_exists = True


@pytest.mark.asyncio
async def test_manager_creates_employee_account() -> None:
    store = RegistrationStoreStub(manager_exists=True)

    result = await RegisterLocalAccountHandler(
        store=store,
        password_encoder=PasswordEncoderStub(),
    ).handle(
        RegisterLocalAccountCommand(
            username=" Employee_1 ",
            password="safe1234",
            role=IdentityRole.EMPLOYEE,
            tenant_id="tenant-default",
            user_id="user-1",
            membership_id="membership-1",
            actor_user_id="actor-1",
        )
    )

    assert result.username == "employee_1"
    assert result.role is IdentityRole.EMPLOYEE
    assert store.records[0].account.password_hash == "hash:safe1234"


@pytest.mark.asyncio
async def test_employee_cannot_create_accounts() -> None:
    with pytest.raises(PermissionDeniedError):
        await RegisterLocalAccountHandler(
            store=RegistrationStoreStub(
                manager_exists=True,
                actor_role=IdentityRole.EMPLOYEE,
            ),
            password_encoder=PasswordEncoderStub(),
        ).handle(
            RegisterLocalAccountCommand(
                username="employee_1",
                password="safe1234",
                role=IdentityRole.EMPLOYEE,
                tenant_id="tenant-default",
                user_id="user-1",
                membership_id="membership-1",
                actor_user_id="actor-1",
            )
        )


@pytest.mark.asyncio
async def test_bootstrap_creates_first_manager_once() -> None:
    store = RegistrationStoreStub()
    handler = BootstrapManagerHandler(store=store, password_encoder=PasswordEncoderStub())
    command = BootstrapManagerCommand(
        username="Initial_Manager",
        password="safe1234",
        tenant_id="tenant-default",
        user_id="manager-1",
        membership_id="membership-1",
    )

    first = await handler.handle(command)
    second = await handler.handle(command)

    assert first.created is True
    assert second.created is False
    assert len(store.records) == 1
    assert store.records[0].role is IdentityRole.MANAGER
