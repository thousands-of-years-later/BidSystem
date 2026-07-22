"""PostgreSQL identity reader behavior."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bid_system.modules.identity.domain.account import AccountStatus
from bid_system.modules.identity.domain.membership import MembershipStatus
from bid_system.modules.identity.infrastructure.models import (
    IdentityAccountModel,
    MembershipRoleModel,
    PermissionModel,
    RefreshSessionModel,
    RoleModel,
    RolePermissionModel,
    TenantMembershipModel,
)
from bid_system.modules.identity.infrastructure.repository import SqlAlchemyIdentityReader


@pytest.mark.asyncio
async def test_reader_resolves_normalized_tenant_grants(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            IdentityAccountModel(
                user_id="user-1",
                login_identifier="user@example.test",
                password_hash="$argon2id$encoded",
                status=AccountStatus.ACTIVE,
                password_version=1,
            ),
            TenantMembershipModel(
                membership_id="membership-1",
                user_id="user-1",
                tenant_id="tenant-1",
                status=MembershipStatus.ACTIVE,
            ),
            PermissionModel(permission_code="documents.read"),
            RoleModel(role_id="role-1", tenant_id="tenant-1", role_code="reviewer"),
            RefreshSessionModel(
                session_id="session-1",
                family_id="family-1",
                user_id="user-1",
                tenant_id="tenant-1",
                token_digest="a" * 64,
                issued_at=now,
                idle_expires_at=now + timedelta(days=7),
                absolute_expires_at=now + timedelta(days=30),
                consumed_at=None,
                revoked_at=None,
            ),
        ]
    )
    await db_session.flush()
    # WHY: models intentionally avoid cross-layer relationship objects; persist FK owners first.
    db_session.add_all(
        [
            RolePermissionModel(role_id="role-1", permission_code="documents.read"),
            MembershipRoleModel(membership_id="membership-1", role_id="role-1"),
        ]
    )
    await db_session.flush()

    reader = SqlAlchemyIdentityReader(db_session)
    account = await reader.get_account("user-1")
    membership = await reader.get_membership("user-1", "tenant-1")
    session = await reader.get_session("session-1")

    assert account is not None and account.can_authenticate
    assert membership is not None
    assert membership.roles == frozenset({"reviewer"})
    assert membership.permissions == frozenset({"documents.read"})
    assert session is not None and session.family_id == "family-1"


@pytest.mark.asyncio
async def test_refresh_rotation_consumes_once_and_replay_revokes_family(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    db_session.add(
        IdentityAccountModel(
            user_id="rotation-user-1",
            login_identifier="rotation@example.test",
            password_hash="$argon2id$encoded",
            status=AccountStatus.ACTIVE,
            password_version=1,
        )
    )
    await db_session.flush()
    db_session.add(
        RefreshSessionModel(
            session_id="rotation-session-1",
            family_id="rotation-family-1",
            user_id="rotation-user-1",
            tenant_id="tenant-1",
            token_digest="b" * 64,
            issued_at=now,
            idle_expires_at=now + timedelta(days=7),
            absolute_expires_at=now + timedelta(days=30),
            consumed_at=None,
            revoked_at=None,
        )
    )
    await db_session.flush()
    reader = SqlAlchemyIdentityReader(db_session)

    rotated = await reader.rotate_refresh_session(
        presented_digest="b" * 64,
        replacement_session_id="rotation-session-2",
        replacement_digest="c" * 64,
        rotated_at=now + timedelta(minutes=1),
        idle_ttl=timedelta(days=7),
    )
    replay = await reader.rotate_refresh_session(
        presented_digest="b" * 64,
        replacement_session_id="rotation-session-3",
        replacement_digest="d" * 64,
        rotated_at=now + timedelta(minutes=2),
        idle_ttl=timedelta(days=7),
    )

    assert rotated.status.value == "rotated"
    assert replay.status.value == "replay_revoked"
