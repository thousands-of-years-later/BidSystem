"""SQLAlchemy models exclusively owned by the identity module."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from bid_system.modules.identity.domain.account import AccountStatus
from bid_system.modules.identity.domain.membership import MembershipStatus
from bid_system.platform.database.models import OrmBase

IDENTITY_SCHEMA = "identity"
ID_LENGTH = 64
LOGIN_IDENTIFIER_LENGTH = 320
CODE_LENGTH = 200
TOKEN_DIGEST_LENGTH = 64


def _enum_values(enum_type: type[AccountStatus] | type[MembershipStatus]) -> list[str]:
    return [member.value for member in enum_type]


class IdentityAccountModel(OrmBase):
    """Persistent local account; password hashes never leave identity infrastructure."""

    __tablename__ = "identity_account"
    __table_args__ = (
        CheckConstraint("password_version >= 1", name="password_version_positive"),
        {"schema": IDENTITY_SCHEMA},
    )

    user_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    login_identifier: Mapped[str] = mapped_column(
        String(LOGIN_IDENTIFIER_LENGTH), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(
            AccountStatus,
            name="account_status",
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    password_version: Mapped[int] = mapped_column(Integer, nullable=False)


class TenantMembershipModel(OrmBase):
    """One account's membership in one tenant."""

    __tablename__ = "tenant_membership"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="user_tenant"),
        {"schema": IDENTITY_SCHEMA},
    )

    membership_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.identity_account.user_id"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(
            MembershipStatus,
            name="membership_status",
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )


class PermissionModel(OrmBase):
    """Stable technical permission code referenced by tenant roles."""

    __tablename__ = "permission"
    __table_args__ = ({"schema": IDENTITY_SCHEMA},)

    permission_code: Mapped[str] = mapped_column(String(CODE_LENGTH), primary_key=True)


class RoleModel(OrmBase):
    """Tenant-owned role whose meaning is a set of generic permissions."""

    __tablename__ = "role"
    __table_args__ = (
        UniqueConstraint("tenant_id", "role_code", name="tenant_role_code"),
        {"schema": IDENTITY_SCHEMA},
    )

    role_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    role_code: Mapped[str] = mapped_column(String(CODE_LENGTH), nullable=False)


class RolePermissionModel(OrmBase):
    """Normalized many-to-many mapping from roles to permission codes."""

    __tablename__ = "role_permission"
    __table_args__ = ({"schema": IDENTITY_SCHEMA},)

    role_id: Mapped[str] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.role.role_id"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.permission.permission_code"), primary_key=True
    )


class MembershipRoleModel(OrmBase):
    """Normalized role assignment for a tenant membership."""

    __tablename__ = "membership_role"
    __table_args__ = ({"schema": IDENTITY_SCHEMA},)

    membership_id: Mapped[str] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.tenant_membership.membership_id"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.role.role_id"), primary_key=True
    )


class RefreshSessionModel(OrmBase):
    """Single-use refresh credential record containing only its SHA-256 digest."""

    __tablename__ = "refresh_session"
    __table_args__ = (
        Index("ix_refresh_session_family", "family_id"),
        Index("ix_refresh_session_active_expiry", "idle_expires_at", "absolute_expires_at"),
        {"schema": IDENTITY_SCHEMA},
    )

    session_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.identity_account.user_id"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    token_digest: Mapped[str] = mapped_column(
        String(TOKEN_DIGEST_LENGTH), nullable=False, unique=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
