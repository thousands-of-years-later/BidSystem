"""Trusted tenant-context construction tests."""

import pytest

from bid_system.platform.security.authentication import AuthenticatedPrincipal
from bid_system.platform.security.tenant import TenantContext, TenantContextError


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id="user-1",
        tenant_id="tenant-1",
        session_id="session-1",
        roles=frozenset(),
        permissions=frozenset(),
        active=True,
    )


def test_builds_context_only_from_matching_authenticated_tenant() -> None:
    context = TenantContext.from_principal(_principal(), requested_tenant_id="tenant-1")

    assert context.tenant_id == "tenant-1"
    assert context.user_id == "user-1"


def test_rejects_client_selected_cross_tenant_context() -> None:
    with pytest.raises(TenantContextError, match="Tenant context is invalid"):
        TenantContext.from_principal(_principal(), requested_tenant_id="tenant-2")

