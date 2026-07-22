"""Tenant-aware generic RBAC mechanics without resource-domain rules."""

from dataclasses import dataclass
from enum import StrEnum

from bid_system.platform.security.authentication import AuthenticatedPrincipal
from bid_system.shared.contracts.errors import PermissionDeniedError


class DenialReason(StrEnum):
    """Non-sensitive authorization denial categories for audit metadata."""

    INACTIVE_PRINCIPAL = "inactive_principal"
    TENANT_MISMATCH = "tenant_mismatch"
    MISSING_PERMISSION = "missing_permission"


@dataclass(frozen=True)
class AuthorizationDecision:
    """Result of platform-level permission and tenant checks."""

    allowed: bool
    denial_reason: DenialReason | None


class PermissionEvaluator:
    """Evaluate only generic grants; modules still decide resource ownership and state rules."""

    @staticmethod
    def evaluate(
        principal: AuthenticatedPrincipal,
        *,
        required_permissions: frozenset[str],
        tenant_id: str,
    ) -> AuthorizationDecision:
        if not principal.active:
            return AuthorizationDecision(False, DenialReason.INACTIVE_PRINCIPAL)
        if principal.tenant_id != tenant_id:
            return AuthorizationDecision(False, DenialReason.TENANT_MISMATCH)
        if not required_permissions.issubset(principal.permissions):
            return AuthorizationDecision(False, DenialReason.MISSING_PERMISSION)
        return AuthorizationDecision(True, None)

    @staticmethod
    def require(decision: AuthorizationDecision) -> None:
        if not decision.allowed:
            raise PermissionDeniedError

