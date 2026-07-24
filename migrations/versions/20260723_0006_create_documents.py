"""Create append-only document and document-version storage.

Revision ID: 20260723_0006
Revises: 20260723_0005
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0006"
down_revision: str | None = "20260723_0005"
branch_labels: str | None = None
depends_on: str | None = None

DOCUMENTS_SCHEMA = "documents"


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema(DOCUMENTS_SCHEMA))
    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_document"),
        schema=DOCUMENTS_SCHEMA,
    )
    op.create_index(
        "ix_document_tenant",
        "document",
        ["tenant_id"],
        unique=False,
        schema=DOCUMENTS_SCHEMA,
    )
    op.create_table(
        "document_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("normalized_pdf_url", sa.Text(), nullable=False),
        sa.Column(
            "file_format",
            sa.Enum(
                "pdf",
                "docx",
                "pptx",
                name="document_format",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_pdf_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column("parse_duration_ms", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "page_count BETWEEN 1 AND 500",
            name="ck_document_version_page_count_supported",
        ),
        sa.CheckConstraint(
            "parse_duration_ms >= 0",
            name="ck_document_version_parse_duration_non_negative",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_document_version_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            [f"{DOCUMENTS_SCHEMA}.document.id"],
            name="fk_document_version_document_id_document",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_version"),
        sa.UniqueConstraint(
            "document_id",
            "file_hash",
            name="uq_document_version_document_file_hash",
        ),
        sa.UniqueConstraint(
            "document_id",
            "version",
            name="uq_document_version_document_version_sequence",
        ),
        schema=DOCUMENTS_SCHEMA,
    )
    op.create_index(
        "ix_document_version_tenant_document",
        "document_version",
        ["tenant_id", "document_id"],
        unique=False,
        schema=DOCUMENTS_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_version_tenant_document",
        table_name="document_version",
        schema=DOCUMENTS_SCHEMA,
    )
    op.drop_table("document_version", schema=DOCUMENTS_SCHEMA)
    op.drop_index(
        "ix_document_tenant",
        table_name="document",
        schema=DOCUMENTS_SCHEMA,
    )
    op.drop_table("document", schema=DOCUMENTS_SCHEMA)
    op.execute(sa.schema.DropSchema(DOCUMENTS_SCHEMA))
