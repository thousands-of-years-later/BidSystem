"""Typed request-scoped dependency accessors."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from fastapi import Request

from bid_system.bootstrap.dependencies import get_database_resource
from bid_system.platform.database.transaction import AsyncTransactionManager


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
