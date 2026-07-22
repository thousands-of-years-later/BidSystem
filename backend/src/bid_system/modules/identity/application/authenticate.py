"""Local account authentication and initial refresh-session issuance."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from bid_system.modules.identity.application.ports import AuthenticationStore, PasswordVerifier
from bid_system.modules.identity.domain.session import RefreshSession
from bid_system.shared.contracts.errors import AuthenticationError


@dataclass(frozen=True)
class AuthenticateLocalAccountCommand:
    """Validated login input plus caller-provided time and identifiers."""

    login_identifier: str
    password: str
    tenant_id: str
    session_id: str
    family_id: str
    refresh_token_digest: str
    authenticated_at: datetime
    idle_ttl: timedelta
    absolute_ttl: timedelta


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Tenant grants and the newly persisted refresh session."""

    user_id: str
    tenant_id: str
    session_id: str
    roles: frozenset[str]
    permissions: frozenset[str]


class AuthenticateLocalAccountHandler:
    """Authenticate without leaking whether account, password, or membership failed."""

    def __init__(self, *, store: AuthenticationStore, password_verifier: PasswordVerifier) -> None:
        self._store = store
        self._password_verifier = password_verifier

    async def handle(self, command: AuthenticateLocalAccountCommand) -> AuthenticatedIdentity:
        normalized_login = command.login_identifier.strip().casefold()
        account = await self._store.get_account_by_login(normalized_login)
        password_check = self._password_verifier.verify(
            command.password,
            None if account is None else account.password_hash,
        )
        if account is None or not account.can_authenticate or not password_check.valid:
            raise AuthenticationError
        membership = await self._store.get_membership(account.user_id, command.tenant_id)
        if membership is None or not membership.active:
            raise AuthenticationError
        if password_check.updated_hash is not None:
            account = account.replace_password(password_hash=password_check.updated_hash)
            await self._store.update_password_hash(account)
        refresh_session = RefreshSession.issue(
            session_id=command.session_id,
            family_id=command.family_id,
            user_id=account.user_id,
            tenant_id=membership.tenant_id,
            token_digest=command.refresh_token_digest,
            issued_at=command.authenticated_at,
            idle_ttl=command.idle_ttl,
            absolute_ttl=command.absolute_ttl,
        )
        await self._store.add_refresh_session(refresh_session)
        return AuthenticatedIdentity(
            user_id=account.user_id,
            tenant_id=membership.tenant_id,
            session_id=refresh_session.session_id,
            roles=membership.roles,
            permissions=membership.permissions,
        )
