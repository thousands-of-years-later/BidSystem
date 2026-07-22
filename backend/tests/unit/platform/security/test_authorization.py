"""Generic RBAC tests; business resource rules are intentionally absent."""

import pytest

from bid_system.platform.security.authentication import AuthenticatedPrincipal
from bid_system.platform.security.authorization import PermissionEvaluator
from bid_system.shared.contracts.errors import PermissionDeniedError


def _principal(*, tenant_id: str = "tenant-1", active: bool = True) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id="user-1",
        tenant_id=tenant_id,
        session_id="session-1",
        roles=frozenset({"reviewer"}),
        permissions=frozenset({"documents.read", "documents.download"}),
        active=active,
    )


def test_allows_only_when_every_permission_and_tenant_match() -> None:
    decision = PermissionEvaluator.evaluate(
        _principal(),
        required_permissions=frozenset({"documents.read", "documents.download"}),
        tenant_id="tenant-1",
    )

    assert decision.allowed is True


@pytest.mark.parametrize(
    "principal,tenant_id,required",
    (
        (_principal(tenant_id="tenant-2"), "tenant-1", frozenset({"documents.read"})),
        (_principal(active=False), "tenant-1", frozenset({"documents.read"})),
        (_principal(), "tenant-1", frozenset({"documents.delete"})),
    ),
)
def test_denies_cross_tenant_inactive_or_missing_permission(
    principal: AuthenticatedPrincipal,
    tenant_id: str,
    required: frozenset[str],
) -> None:
    decision = PermissionEvaluator.evaluate(
        principal,
        required_permissions=required,
        tenant_id=tenant_id,
    )

    assert decision.allowed is False
    with pytest.raises(PermissionDeniedError):
        PermissionEvaluator.require(decision)

