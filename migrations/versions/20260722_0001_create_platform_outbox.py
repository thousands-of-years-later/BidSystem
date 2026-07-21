"""Create the platform transactional outbox.

Revision ID: 20260722_0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260722_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

PLATFORM_SCHEMA = "platform"


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema(PLATFORM_SCHEMA, if_not_exists=True))
    op.create_table(
        "outbox_event",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=200), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=200), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "published",
                "dead_letter",
                name="outbox_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        sa.PrimaryKeyConstraint("event_id", name="pk_outbox_event"),
        schema=PLATFORM_SCHEMA,
    )
    op.create_index(
        "ix_outbox_event_delivery",
        "outbox_event",
        ["status", "available_at"],
        unique=False,
        schema=PLATFORM_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_event_delivery", table_name="outbox_event", schema=PLATFORM_SCHEMA)
    op.drop_table("outbox_event", schema=PLATFORM_SCHEMA)
    op.execute(sa.schema.DropSchema(PLATFORM_SCHEMA))
