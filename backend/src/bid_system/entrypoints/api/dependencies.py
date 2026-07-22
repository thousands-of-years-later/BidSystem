"""Typed request-scoped dependency accessors."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Annotated, Protocol, runtime_checkable

from fastapi import Depends, Request

from bid_system.bootstrap.container import ApplicationContainer, LifecycleResource
from bid_system.bootstrap.dependencies import build_identity_reader
from bid_system.modules.identity.application.ports import IdentityReader
from bid_system.modules.identity.application.resolve_identity import (
    ResolveIdentityHandler,
    ResolveIdentityQuery,
)
from bid_system.platform.config import AppSettings, AuthSettings
from bid_system.platform.database.transaction import AsyncTransactionManager
from bid_system.platform.security.authentication import (
    AccessTokenVerifier,
    AuthenticatedPrincipal,
    BearerTokenParser,
    TokenValidationError,
)
from bid_system.shared.contracts.errors import AuthenticationError


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


@runtime_checkable
class DatabaseTransactionResource(Protocol):
    """Database capability required by the HTTP transaction dependency."""

    def transaction(self) -> AsyncTransactionManager: ...


@dataclass(frozen=True)
class RequestContext:
    """Trusted context created at the HTTP boundary for one request."""

    request_id: str
    trace_id: str
    user_id: str | None
    tenant_id: str | None
    method: str
    path: str
    client_ip: str | None
    started_at: datetime


def get_request_context(request: Request) -> RequestContext:
    """Return context initialized by the outer request middleware."""
    context: RequestContext = request.state.request_context
    return context


async def get_database_transaction(request: Request) -> AsyncGenerator[AsyncTransactionManager]:
    """Commit one request transaction or roll it back, then always release its session."""
    resource = get_database_resource(request)
    if not isinstance(resource, DatabaseTransactionResource):
        raise RuntimeError("Initialized database resource cannot create transactions")
    async with resource.transaction() as transaction:
        yield transaction


async def resolve_current_principal(
    *,
    authorization_header: str | None,
    auth_settings: AuthSettings,
    identity_reader: IdentityReader,
    resolved_at: datetime,
) -> AuthenticatedPrincipal:
    """Resolve a bearer credential against cryptography and current identity state."""
    try:
        token = BearerTokenParser.parse(authorization_header)
        claims = AccessTokenVerifier(auth_settings).verify(token, verified_at=resolved_at)
    except TokenValidationError:
        raise AuthenticationError from None
    identity = await ResolveIdentityHandler(identity_reader).handle(
        ResolveIdentityQuery(
            user_id=claims.subject,
            tenant_id=claims.tenant_id,
            session_id=claims.session_id,
            resolved_at=resolved_at,
        )
    )
    return AuthenticatedPrincipal(
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        session_id=identity.session_id,
        roles=identity.roles,
        permissions=identity.permissions,
        active=True,
    )


async def get_current_principal(
    request: Request,
    transaction: Annotated[AsyncTransactionManager, Depends(get_database_transaction)],
) -> AuthenticatedPrincipal:
    """FastAPI dependency that stores only verified identity in request context."""
    principal = await resolve_current_principal(
        authorization_header=request.headers.get("Authorization"),
        auth_settings=get_settings(request).auth,
        identity_reader=build_identity_reader(transaction),
        resolved_at=datetime.now(UTC),
    )
    context = get_request_context(request)
    request.state.request_context = replace(
        context,
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
    )
    request.state.current_principal = principal
    return principal
