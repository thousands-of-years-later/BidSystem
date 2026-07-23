"""Application-start identity provisioning with transaction-safe idempotency."""

from typing import Protocol, runtime_checkable
from uuid import uuid4

from bid_system.bootstrap.container import ApplicationContainer, LifecycleResource
from bid_system.bootstrap.dependencies import (
    build_identity_authentication_repository,
    build_password_encoder,
)
from bid_system.modules.identity.application.register import (
    BootstrapManagerCommand,
    BootstrapManagerHandler,
)
from bid_system.platform.database.transaction import AsyncTransactionManager


@runtime_checkable
class TransactionResource(LifecycleResource, Protocol):
    """Database resource capability needed during identity provisioning."""

    def transaction(self) -> AsyncTransactionManager: ...


async def provision_initial_manager(container: ApplicationContainer) -> None:
    """Create the configured initial manager before the API accepts traffic."""
    settings = container.settings.auth
    if not settings.enabled:
        return
    username = settings.initial_manager_username
    password_secret = settings.initial_manager_password
    if username is None or password_secret is None:
        raise RuntimeError("Initial manager configuration is incomplete")
    database: LifecycleResource | None = container.database
    if not isinstance(database, TransactionResource):
        raise RuntimeError("Initialized database resource cannot create transactions")
    async with database.transaction() as transaction:
        await BootstrapManagerHandler(
            store=build_identity_authentication_repository(transaction),
            password_encoder=build_password_encoder(settings),
        ).handle(
            BootstrapManagerCommand(
                username=username,
                password=password_secret.get_secret_value(),
                tenant_id=settings.default_tenant_id,
                user_id=str(uuid4()),
                membership_id=str(uuid4()),
            )
        )
