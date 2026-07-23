"""Manager-authorized account registration and idempotent initial-manager bootstrap."""

from dataclasses import dataclass

from bid_system.modules.identity.application.ports import (
    PasswordEncoder,
    RegistrationRecord,
    RegistrationStore,
)
from bid_system.modules.identity.domain.access import (
    IdentityRole,
    RegistrationCredentials,
    permissions_for_role,
)
from bid_system.modules.identity.domain.account import LocalAccount
from bid_system.modules.identity.domain.membership import TenantMembership
from bid_system.shared.contracts.errors import PermissionDeniedError


@dataclass(frozen=True)
class RegisterLocalAccountCommand:
    """Validated account request plus trusted actor and generated identifiers."""

    username: str
    password: str
    role: IdentityRole
    tenant_id: str
    user_id: str
    membership_id: str
    actor_user_id: str


@dataclass(frozen=True)
class RegisteredAccount:
    """Non-sensitive account facts returned after registration."""

    user_id: str
    username: str
    role: IdentityRole


class RegisterLocalAccountHandler:
    """Create an account only for a trusted manager actor."""

    def __init__(self, *, store: RegistrationStore, password_encoder: PasswordEncoder) -> None:
        self._store = store
        self._password_encoder = password_encoder

    async def handle(self, command: RegisterLocalAccountCommand) -> RegisteredAccount:
        actor_membership = await self._store.get_membership(
            command.actor_user_id,
            command.tenant_id,
        )
        if (
            actor_membership is None
            or not actor_membership.active
            or IdentityRole.MANAGER.value not in actor_membership.roles
        ):
            raise PermissionDeniedError
        return await _create_account(
            store=self._store,
            password_encoder=self._password_encoder,
            username=command.username,
            password=command.password,
            role=command.role,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
            membership_id=command.membership_id,
        )


@dataclass(frozen=True)
class BootstrapManagerCommand:
    """Deployment-supplied credentials and generated identity identifiers."""

    username: str
    password: str
    tenant_id: str
    user_id: str
    membership_id: str


@dataclass(frozen=True)
class BootstrapManagerResult:
    """Whether this startup transaction created the initial manager."""

    created: bool


class BootstrapManagerHandler:
    """Create exactly one initial manager under the repository bootstrap lock."""

    def __init__(self, *, store: RegistrationStore, password_encoder: PasswordEncoder) -> None:
        self._store = store
        self._password_encoder = password_encoder

    async def handle(self, command: BootstrapManagerCommand) -> BootstrapManagerResult:
        if await self._store.manager_exists_for_update(command.tenant_id):
            return BootstrapManagerResult(created=False)
        await _create_account(
            store=self._store,
            password_encoder=self._password_encoder,
            username=command.username,
            password=command.password,
            role=IdentityRole.MANAGER,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
            membership_id=command.membership_id,
        )
        return BootstrapManagerResult(created=True)


async def _create_account(
    *,
    store: RegistrationStore,
    password_encoder: PasswordEncoder,
    username: str,
    password: str,
    role: IdentityRole,
    tenant_id: str,
    user_id: str,
    membership_id: str,
) -> RegisteredAccount:
    credentials = RegistrationCredentials.create(username=username, password=password)
    account = LocalAccount.register(
        user_id=user_id,
        login_identifier=credentials.username,
        password_hash=password_encoder.hash(credentials.password),
    )
    membership = TenantMembership.create(
        membership_id=membership_id,
        user_id=user_id,
        tenant_id=tenant_id,
        roles=frozenset({role.value}),
        permissions=frozenset(permission.value for permission in permissions_for_role(role)),
    )
    await store.add_registration(
        RegistrationRecord(account=account, membership=membership, role=role)
    )
    return RegisteredAccount(user_id=user_id, username=credentials.username, role=role)
