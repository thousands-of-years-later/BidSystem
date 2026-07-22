"""SQLAlchemy identity adapter returning domain objects and atomic refresh outcomes."""

from datetime import datetime, timedelta

from sqlalchemy import distinct, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bid_system.modules.identity.application.ports import (
    RefreshRotationResult,
    RefreshRotationStatus,
)
from bid_system.modules.identity.domain.account import LocalAccount
from bid_system.modules.identity.domain.membership import TenantMembership
from bid_system.modules.identity.domain.session import (
    InvalidRefreshSessionError,
    RefreshSession,
    RefreshTokenReplayError,
)
from bid_system.modules.identity.infrastructure.models import (
    IdentityAccountModel,
    MembershipRoleModel,
    PermissionModel,
    RefreshSessionModel,
    RoleModel,
    RolePermissionModel,
    TenantMembershipModel,
)


class SqlAlchemyIdentityReader:
    """Read identity-owned tables inside the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_account(self, user_id: str) -> LocalAccount | None:
        result = await self._session.execute(
            select(IdentityAccountModel).where(IdentityAccountModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return LocalAccount(
            user_id=model.user_id,
            login_identifier=model.login_identifier,
            password_hash=model.password_hash,
            status=model.status,
            password_version=model.password_version,
        )

    async def get_account_by_login(self, login_identifier: str) -> LocalAccount | None:
        result = await self._session.execute(
            select(IdentityAccountModel).where(
                IdentityAccountModel.login_identifier == login_identifier
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return LocalAccount(
            user_id=model.user_id,
            login_identifier=model.login_identifier,
            password_hash=model.password_hash,
            status=model.status,
            password_version=model.password_version,
        )

    async def update_password_hash(self, account: LocalAccount) -> None:
        await self._session.execute(
            update(IdentityAccountModel)
            .where(IdentityAccountModel.user_id == account.user_id)
            .values(
                password_hash=account.password_hash,
                password_version=account.password_version,
            )
        )

    async def add_refresh_session(self, session: RefreshSession) -> None:
        self._session.add(
            RefreshSessionModel(
                session_id=session.session_id,
                family_id=session.family_id,
                user_id=session.user_id,
                tenant_id=session.tenant_id,
                token_digest=session.token_digest,
                issued_at=session.issued_at,
                idle_expires_at=session.idle_expires_at,
                absolute_expires_at=session.absolute_expires_at,
                consumed_at=session.consumed_at,
                revoked_at=session.revoked_at,
            )
        )

    async def rotate_refresh_session(
        self,
        *,
        presented_digest: str,
        replacement_session_id: str,
        replacement_digest: str,
        rotated_at: datetime,
        idle_ttl: timedelta,
    ) -> RefreshRotationResult:
        result = await self._session.execute(
            select(RefreshSessionModel)
            .where(RefreshSessionModel.token_digest == presented_digest)
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            return RefreshRotationResult(RefreshRotationStatus.INVALID, None)
        current = self._refresh_session_from_model(model)
        try:
            consumed, replacement = current.rotate(
                presented_digest=presented_digest,
                replacement_session_id=replacement_session_id,
                replacement_token_digest=replacement_digest,
                rotated_at=rotated_at,
                idle_ttl=idle_ttl,
            )
        except RefreshTokenReplayError:
            # WHY: return instead of raising so the caller can commit family revocation before 401.
            await self._session.execute(
                update(RefreshSessionModel)
                .where(
                    RefreshSessionModel.family_id == current.family_id,
                    RefreshSessionModel.revoked_at.is_(None),
                )
                .values(revoked_at=rotated_at)
            )
            return RefreshRotationResult(RefreshRotationStatus.REPLAY_REVOKED, None)
        except InvalidRefreshSessionError:
            return RefreshRotationResult(RefreshRotationStatus.INVALID, None)
        model.consumed_at = consumed.consumed_at
        await self.add_refresh_session(replacement)
        return RefreshRotationResult(RefreshRotationStatus.ROTATED, replacement)

    async def revoke_refresh_family_by_digest(
        self,
        *,
        token_digest: str,
        revoked_at: datetime,
    ) -> bool:
        family_result = await self._session.execute(
            select(RefreshSessionModel.family_id).where(
                RefreshSessionModel.token_digest == token_digest
            )
        )
        family_id = family_result.scalar_one_or_none()
        if family_id is None:
            return False
        await self._session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.family_id == family_id,
                RefreshSessionModel.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        return True

    async def get_membership(
        self,
        user_id: str,
        tenant_id: str,
    ) -> TenantMembership | None:
        membership_result = await self._session.execute(
            select(TenantMembershipModel).where(
                TenantMembershipModel.user_id == user_id,
                TenantMembershipModel.tenant_id == tenant_id,
            )
        )
        model = membership_result.scalar_one_or_none()
        if model is None:
            return None
        roles_result = await self._session.execute(
            select(RoleModel.role_code)
            .join(MembershipRoleModel, MembershipRoleModel.role_id == RoleModel.role_id)
            .where(
                MembershipRoleModel.membership_id == model.membership_id,
                RoleModel.tenant_id == model.tenant_id,
            )
        )
        permissions_result = await self._session.execute(
            select(distinct(PermissionModel.permission_code))
            .join(
                RolePermissionModel,
                RolePermissionModel.permission_code == PermissionModel.permission_code,
            )
            .join(
                MembershipRoleModel,
                MembershipRoleModel.role_id == RolePermissionModel.role_id,
            )
            .join(RoleModel, RoleModel.role_id == MembershipRoleModel.role_id)
            .where(
                MembershipRoleModel.membership_id == model.membership_id,
                RoleModel.tenant_id == model.tenant_id,
            )
        )
        return TenantMembership(
            membership_id=model.membership_id,
            user_id=model.user_id,
            tenant_id=model.tenant_id,
            roles=frozenset(roles_result.scalars().all()),
            permissions=frozenset(permissions_result.scalars().all()),
            status=model.status,
        )

    async def get_session(self, session_id: str) -> RefreshSession | None:
        result = await self._session.execute(
            select(RefreshSessionModel).where(RefreshSessionModel.session_id == session_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._refresh_session_from_model(model)

    @staticmethod
    def _refresh_session_from_model(model: RefreshSessionModel) -> RefreshSession:
        return RefreshSession(
            session_id=model.session_id,
            family_id=model.family_id,
            user_id=model.user_id,
            tenant_id=model.tenant_id,
            token_digest=model.token_digest,
            issued_at=model.issued_at,
            idle_expires_at=model.idle_expires_at,
            absolute_expires_at=model.absolute_expires_at,
            consumed_at=model.consumed_at,
            revoked_at=model.revoked_at,
        )
