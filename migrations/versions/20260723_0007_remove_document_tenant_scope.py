"""Remove tenant ownership from globally shared documents.

Revision ID: 20260723_0007
Revises: 20260723_0006
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0007"
down_revision: str | None = "20260723_0006"
branch_labels: str | None = None
depends_on: str | None = None

DOCUMENTS_SCHEMA = "documents"
DEFAULT_TENANT_ID = "default"


def upgrade() -> None:
    op.drop_index(
        "ix_document_version_tenant_document",
        table_name="document_version",
        schema=DOCUMENTS_SCHEMA,
    )
    op.drop_column(
        "document_version",
        "tenant_id",
        schema=DOCUMENTS_SCHEMA,
    )
    op.drop_index(
        "ix_document_tenant",
        table_name="document",
        schema=DOCUMENTS_SCHEMA,
    )
    op.drop_column(
        "document",
        "tenant_id",
        schema=DOCUMENTS_SCHEMA,
    )


def downgrade() -> None:
    op.add_column(
        "document",
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            nullable=False,
            server_default=DEFAULT_TENANT_ID,
        ),
        schema=DOCUMENTS_SCHEMA,
    )
    op.alter_column(
        "document",
        "tenant_id",
        server_default=None,
        schema=DOCUMENTS_SCHEMA,
    )
    op.create_index(
        "ix_document_tenant",
        "document",
        ["tenant_id"],
        unique=False,
        schema=DOCUMENTS_SCHEMA,
    )
    op.add_column(
        "document_version",
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            nullable=False,
            server_default=DEFAULT_TENANT_ID,
        ),
        schema=DOCUMENTS_SCHEMA,
    )
    op.alter_column(
        "document_version",
        "tenant_id",
        server_default=None,
        schema=DOCUMENTS_SCHEMA,
    )
    op.create_index(
        "ix_document_version_tenant_document",
        "document_version",
        ["tenant_id", "document_id"],
        unique=False,
        schema=DOCUMENTS_SCHEMA,
    )
