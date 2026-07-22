"""Tenant membership and generic role grants owned by identity."""

from dataclasses import dataclass, replace
from enum import StrEnum


class MembershipStatus(StrEnum):
    """Whether an account may act within one tenant."""

    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True)
class TenantMembership:
    """Tenant-scoped generic grants; resource decisions remain in business modules."""

    membership_id: str
    user_id: str
    tenant_id: str
    roles: frozenset[str]
    permissions: frozenset[str]
    status: MembershipStatus

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.membership_id, self.user_id, self.tenant_id)):
            raise ValueError("Tenant membership identifiers must not be blank")
        if any(not value.strip() for value in self.roles | self.permissions):
            raise ValueError("Role and permission codes must not be blank")

    @classmethod
    def create(
        cls,
        *,
        membership_id: str,
        user_id: str,
        tenant_id: str,
        roles: frozenset[str],
        permissions: frozenset[str],
    ) -> "TenantMembership":
        return cls(
            membership_id=membership_id,
            user_id=user_id,
            tenant_id=tenant_id,
            roles=roles,
            permissions=permissions,
            status=MembershipStatus.ACTIVE,
        )

    @property
    def active(self) -> bool:
        return self.status is MembershipStatus.ACTIVE

    def disable(self) -> "TenantMembership":
        return replace(self, status=MembershipStatus.DISABLED)
