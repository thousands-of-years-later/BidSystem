"""Trusted request and worker tenant context construction."""

from dataclasses import dataclass

from bid_system.platform.security.authentication import AuthenticatedPrincipal

INVALID_TENANT_CONTEXT_MESSAGE = "Tenant context is invalid"


class TenantContextError(ValueError):
    """A requested tenant is not established by the authenticated principal."""

    def __init__(self) -> None:
        super().__init__(INVALID_TENANT_CONTEXT_MESSAGE)


@dataclass(frozen=True)
class TenantContext:
    """Tenant identity safe to propagate into transactions and audit records."""

    tenant_id: str
    user_id: str
    session_id: str

    @classmethod
    def from_principal(
        cls,
        principal: AuthenticatedPrincipal,
        *,
        requested_tenant_id: str,
    ) -> "TenantContext":
        if (
            not principal.active
            or not requested_tenant_id.strip()
            or requested_tenant_id != principal.tenant_id
        ):
            raise TenantContextError
        return cls(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            session_id=principal.session_id,
        )

