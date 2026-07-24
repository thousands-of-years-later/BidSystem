"""Documents-owned SQLAlchemy table and constraint contract."""

from sqlalchemy import CheckConstraint, UniqueConstraint

from bid_system.modules.documents.infrastructure.models import (
    DOCUMENTS_SCHEMA,
    DocumentModel,
    DocumentVersionModel,
)
from bid_system.platform.database.models import OrmBase


def test_documents_module_registers_its_owned_tables() -> None:
    tables = {
        table.name
        for table in OrmBase.metadata.tables.values()
        if table.schema == DOCUMENTS_SCHEMA
    }

    assert tables == {"document", "document_version"}


def test_document_version_contains_required_metadata_columns() -> None:
    columns = set(DocumentVersionModel.__table__.columns.keys())

    assert columns == {
        "id",
        "document_id",
        "name",
        "file_url",
        "normalized_pdf_url",
        "file_format",
        "file_hash",
        "normalized_pdf_hash",
        "version",
        "uploaded_at",
        "expires_at",
        "page_count",
        "parser_version",
        "parse_duration_ms",
    }


def test_document_version_enforces_sequence_hash_and_bounds() -> None:
    table = OrmBase.metadata.tables[f"{DOCUMENTS_SCHEMA}.document_version"]
    constraints = table.constraints
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in constraints
        if isinstance(constraint, UniqueConstraint)
    }
    check_names = {
        constraint.name
        for constraint in constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert ("document_id", "version") in unique_columns
    assert ("document_id", "file_hash") in unique_columns
    assert {
        "ck_document_version_version_positive",
        "ck_document_version_page_count_supported",
        "ck_document_version_parse_duration_non_negative",
    } <= check_names


def test_document_model_has_no_tenant_ownership_column() -> None:
    assert "tenant_id" not in DocumentModel.__table__.c
