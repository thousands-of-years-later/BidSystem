"""Resolve token identity claims against current authoritative identity state."""

from dataclasses import dataclass
from datetime import datetime

from bid_system.modules.identity.application.ports import IdentityReader
from bid_system.shared.contracts.errors import AuthenticationError


@dataclass(frozen=True)
class ResolveIdentityQuery:
    """Candidate identity supplied by a cryptographically verified access token."""

    user_id: str
    tenant_id: str
    session_id: str
    resolved_at: datetime


@dataclass(frozen=True)
class ResolvedIdentity:
    """Current account and tenant grants safe to map into a platform principal."""

    user_id: str
    tenant_id: str
    session_id: str
    roles: frozenset[str]
    permissions: frozenset[str]


class ResolveIdentityHandler:
    """Reject stale token claims after account, membership, or session changes."""

    def __init__(self, reader: IdentityReader) -> None:
        self._reader = reader

    async def handle(self, query: ResolveIdentityQuery) -> ResolvedIdentity:
        account = await self._reader.get_account(query.user_id)
        membership = await self._reader.get_membership(query.user_id, query.tenant_id)
        session = await self._reader.get_session(query.session_id)
        if (
            account is None
            or not account.can_authenticate
            or membership is None
            or not membership.active
            or session is None
            or session.user_id != query.user_id
            or session.tenant_id != query.tenant_id
            or not session.is_active(checked_at=query.resolved_at)
        ):
            raise AuthenticationError
        return ResolvedIdentity(
            user_id=account.user_id,
            tenant_id=membership.tenant_id,
            session_id=session.session_id,
            roles=membership.roles,
            permissions=membership.permissions,
        )
