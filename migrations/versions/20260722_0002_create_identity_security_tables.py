"""Create local identity, tenant RBAC, and refresh-session tables.

Revision ID: 20260722_0002
Revises: 20260722_0001
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0002"
down_revision: str | None = "20260722_0001"
branch_labels: str | None = None
depends_on: str | None = None

IDENTITY_SCHEMA = "identity"


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema(IDENTITY_SCHEMA, if_not_exists=True))
    op.create_table(
        "identity_account",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("login_identifier", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="account_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("password_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("password_version >= 1", name="password_version_positive"),
        sa.PrimaryKeyConstraint("user_id", name="pk_identity_account"),
        sa.UniqueConstraint("login_identifier", name="uq_identity_account_login_identifier"),
        schema=IDENTITY_SCHEMA,
    )
    op.create_table(
        "permission",
        sa.Column("permission_code", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("permission_code", name="pk_permission"),
        schema=IDENTITY_SCHEMA,
    )
    op.create_table(
        "role",
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("role_code", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("role_id", name="pk_role"),
        sa.UniqueConstraint("tenant_id", "role_code", name="uq_role_tenant_role_code"),
        schema=IDENTITY_SCHEMA,
    )
    op.create_table(
        "tenant_membership",
        sa.Column("membership_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="membership_status", native_enum=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{IDENTITY_SCHEMA}.identity_account.user_id"],
            name="fk_tenant_membership_user_id_identity_account",
        ),
        sa.PrimaryKeyConstraint("membership_id", name="pk_tenant_membership"),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_tenant_membership_user_tenant"),
        schema=IDENTITY_SCHEMA,
    )
    op.create_table(
        "role_permission",
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("permission_code", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            [f"{IDENTITY_SCHEMA}.permission.permission_code"],
            name="fk_role_permission_permission_code_permission",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            [f"{IDENTITY_SCHEMA}.role.role_id"],
            name="fk_role_permission_role_id_role",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_code", name="pk_role_permission"),
        schema=IDENTITY_SCHEMA,
    )
    op.create_table(
        "membership_role",
        sa.Column("membership_id", sa.String(length=64), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            [f"{IDENTITY_SCHEMA}.tenant_membership.membership_id"],
            name="fk_membership_role_membership_id_tenant_membership",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            [f"{IDENTITY_SCHEMA}.role.role_id"],
            name="fk_membership_role_role_id_role",
        ),
        sa.PrimaryKeyConstraint("membership_id", "role_id", name="pk_membership_role"),
        schema=IDENTITY_SCHEMA,
    )
    op.create_table(
        "refresh_session",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{IDENTITY_SCHEMA}.identity_account.user_id"],
            name="fk_refresh_session_user_id_identity_account",
        ),
        sa.PrimaryKeyConstraint("session_id", name="pk_refresh_session"),
        sa.UniqueConstraint("token_digest", name="uq_refresh_session_token_digest"),
        schema=IDENTITY_SCHEMA,
    )
    op.create_index(
        "ix_refresh_session_family",
        "refresh_session",
        ["family_id"],
        schema=IDENTITY_SCHEMA,
    )
    op.create_index(
        "ix_refresh_session_active_expiry",
        "refresh_session",
        ["idle_expires_at", "absolute_expires_at"],
        schema=IDENTITY_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_refresh_session_active_expiry",
        table_name="refresh_session",
        schema=IDENTITY_SCHEMA,
    )
    op.drop_index(
        "ix_refresh_session_family",
        table_name="refresh_session",
        schema=IDENTITY_SCHEMA,
    )
    for table_name in (
        "refresh_session",
        "membership_role",
        "role_permission",
        "tenant_membership",
        "role",
        "permission",
        "identity_account",
    ):
        op.drop_table(table_name, schema=IDENTITY_SCHEMA)
    op.execute(sa.schema.DropSchema(IDENTITY_SCHEMA))
