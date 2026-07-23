"""Seed the default tenant roles and restricted capability catalog.

Revision ID: 20260723_0004
Revises: 20260722_0003
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0004"
down_revision: str | None = "20260722_0003"
branch_labels: str | None = None
depends_on: str | None = None

IDENTITY_SCHEMA = "identity"
DEFAULT_TENANT_ID = "default"
MANAGER_ROLE_ID = "default-manager"
EMPLOYEE_ROLE_ID = "default-employee"
MANAGER_ROLE_CODE = "manager"
EMPLOYEE_ROLE_CODE = "employee"
PERMISSION_CODES = ("accounts.create", "content.upload", "content.modify")


def upgrade() -> None:
    permission = sa.table(
        "permission", sa.column("permission_code", sa.String()), schema=IDENTITY_SCHEMA
    )
    role = sa.table(
        "role",
        sa.column("role_id", sa.String()),
        sa.column("tenant_id", sa.String()),
        sa.column("role_code", sa.String()),
        schema=IDENTITY_SCHEMA,
    )
    role_permission = sa.table(
        "role_permission",
        sa.column("role_id", sa.String()),
        sa.column("permission_code", sa.String()),
        schema=IDENTITY_SCHEMA,
    )
    op.bulk_insert(
        permission,
        [{"permission_code": permission_code} for permission_code in PERMISSION_CODES],
    )
    op.bulk_insert(
        role,
        [
            {
                "role_id": MANAGER_ROLE_ID,
                "tenant_id": DEFAULT_TENANT_ID,
                "role_code": MANAGER_ROLE_CODE,
            },
            {
                "role_id": EMPLOYEE_ROLE_ID,
                "tenant_id": DEFAULT_TENANT_ID,
                "role_code": EMPLOYEE_ROLE_CODE,
            },
        ],
    )
    op.bulk_insert(
        role_permission,
        [
            {"role_id": MANAGER_ROLE_ID, "permission_code": permission_code}
            for permission_code in PERMISSION_CODES
        ],
    )


def downgrade() -> None:
    role_permission = sa.table(
        "role_permission",
        sa.column("role_id", sa.String()),
        sa.column("permission_code", sa.String()),
        schema=IDENTITY_SCHEMA,
    )
    membership_role = sa.table(
        "membership_role", sa.column("role_id", sa.String()), schema=IDENTITY_SCHEMA
    )
    role = sa.table("role", sa.column("role_id", sa.String()), schema=IDENTITY_SCHEMA)
    permission = sa.table(
        "permission", sa.column("permission_code", sa.String()), schema=IDENTITY_SCHEMA
    )
    connection = op.get_bind()
    assigned_role = connection.execute(
        sa.select(membership_role.c.role_id).where(
            membership_role.c.role_id.in_((MANAGER_ROLE_ID, EMPLOYEE_ROLE_ID))
        )
    ).first()
    if assigned_role is not None:
        raise RuntimeError("Cannot downgrade seeded identity roles while accounts use them")
    connection.execute(
        sa.delete(role_permission).where(role_permission.c.role_id == MANAGER_ROLE_ID)
    )
    connection.execute(
        sa.delete(role).where(role.c.role_id.in_((MANAGER_ROLE_ID, EMPLOYEE_ROLE_ID)))
    )
    connection.execute(
        sa.delete(permission).where(permission.c.permission_code.in_(PERMISSION_CODES))
    )
