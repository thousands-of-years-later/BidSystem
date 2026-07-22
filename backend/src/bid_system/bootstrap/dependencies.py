"""FastAPI dependency accessors for resources assembled by lifespan."""

from fastapi import Request

from bid_system.bootstrap.container import ApplicationContainer, LifecycleResource
from bid_system.modules.identity.application.ports import (
    IdentityAuthenticationRepository,
    IdentityReader,
    PasswordVerifier,
)
from bid_system.modules.identity.infrastructure.passwords import Argon2PasswordVerifier
from bid_system.modules.identity.infrastructure.repository import SqlAlchemyIdentityReader
from bid_system.platform.config import AppSettings, AuthSettings
from bid_system.platform.database.transaction import AsyncTransactionManager
from bid_system.platform.security.authentication import PasswordHasher


def get_container(request: Request) -> ApplicationContainer:
    """Return the application-scoped dependency container."""
    container: ApplicationContainer = request.app.state.container
    return container


def get_settings(request: Request) -> AppSettings:
    """Return validated settings through the application container."""
    return get_container(request).settings


def _required_resource(resource: LifecycleResource | None, name: str) -> LifecycleResource:
    if resource is None:
        raise RuntimeError(f"Application resource is not initialized: {name}")
    return resource


def get_database_resource(request: Request) -> LifecycleResource:
    """Return the initialized database resource."""
    return _required_resource(get_container(request).database, "database")


def get_redis_resource(request: Request) -> LifecycleResource:
    """Return the initialized Redis resource."""
    return _required_resource(get_container(request).redis, "redis")


def get_minio_resource(request: Request) -> LifecycleResource:
    """Return the initialized MinIO resource."""
    return _required_resource(get_container(request).minio, "minio")


def build_identity_reader(transaction: AsyncTransactionManager) -> IdentityReader:
    """Wire the identity query port to the caller's request transaction."""
    return SqlAlchemyIdentityReader(transaction.session)


def build_identity_authentication_repository(
    transaction: AsyncTransactionManager,
) -> IdentityAuthenticationRepository:
    """Wire all local-authentication persistence ports to one request transaction."""
    return SqlAlchemyIdentityReader(transaction.session)


def build_password_verifier(settings: AuthSettings) -> PasswordVerifier:
    """Wire identity password verification to the configured Argon2id adapter."""
    return Argon2PasswordVerifier(
        PasswordHasher(
            memory_cost_kib=settings.argon2_memory_cost_kib,
            time_cost=settings.argon2_time_cost,
            parallelism=settings.argon2_parallelism,
        )
    )
