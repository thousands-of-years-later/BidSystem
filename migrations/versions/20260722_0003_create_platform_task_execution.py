"""Create the platform task execution ledger.

Revision ID: 20260722_0003
Revises: 20260722_0002
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0003"
down_revision: str | None = "20260722_0002"
branch_labels: str | None = None
depends_on: str | None = None

PLATFORM_SCHEMA = "platform"


def upgrade() -> None:
    op.create_table(
        "task_execution",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=200), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "retry_scheduled",
                "succeeded",
                "dead_letter",
                name="task_execution_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_count >= 1", name="attempt_count_positive"),
        sa.PrimaryKeyConstraint("task_id", name="pk_task_execution"),
        schema=PLATFORM_SCHEMA,
    )
    op.create_index(
        "ix_task_execution_delivery",
        "task_execution",
        ["status", "available_at"],
        unique=False,
        schema=PLATFORM_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_execution_delivery",
        table_name="task_execution",
        schema=PLATFORM_SCHEMA,
    )
    op.drop_table("task_execution", schema=PLATFORM_SCHEMA)
