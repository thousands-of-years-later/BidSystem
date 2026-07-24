"""Document aggregate and immutable version rules."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from bid_system.modules.documents.domain.models import (
    Document,
    DocumentFormat,
    DocumentVersion,
)

FILE_HASH = "a" * 64
PDF_HASH = "b" * 64
UPLOADED_AT = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)


def _version(
    *,
    version: int = 1,
    file_hash: str = FILE_HASH,
    page_count: int = 2,
) -> DocumentVersion:
    document_id = uuid4()
    return DocumentVersion(
        id=uuid4(),
        document_id=document_id,
        name="投标文件.docx",
        file_url=f"minio://bid-system/raw/{file_hash}",
        normalized_pdf_url=f"minio://bid-system/pdf/{PDF_HASH}",
        file_format=DocumentFormat.DOCX,
        file_hash=file_hash,
        normalized_pdf_hash=PDF_HASH,
        version=version,
        uploaded_at=UPLOADED_AT,
        expires_at=None,
        page_count=page_count,
        parser_version="document-metadata-v1",
        parse_duration_ms=125,
    )


def test_document_format_contains_only_supported_values() -> None:
    assert {item.value for item in DocumentFormat} == {"pdf", "docx", "pptx"}


def test_document_version_accepts_complete_metadata() -> None:
    version = _version()

    assert version.version == 1
    assert version.page_count == 2
    assert version.parse_duration_ms == 125


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " "),
        ("file_hash", "invalid"),
        ("normalized_pdf_hash", "invalid"),
        ("version", 0),
        ("page_count", 0),
        ("page_count", 501),
        ("parser_version", ""),
        ("parse_duration_ms", -1),
    ],
)
def test_document_version_rejects_invalid_metadata(field: str, value: str | int) -> None:
    values = _version().__dict__ | {field: value}

    with pytest.raises(ValueError):
        DocumentVersion(**values)


def test_document_starts_at_version_one() -> None:
    first = _version()

    document = Document.create(
        document_id=first.document_id,
        first_version=first,
    )

    assert document.versions == (first,)
    assert document.latest_version == first


def test_document_appends_different_content_with_next_version() -> None:
    first = _version()
    document = Document.create(
        document_id=first.document_id,
        first_version=first,
    )
    replacement = DocumentVersion(
        **(
            first.__dict__
            | {
                "id": uuid4(),
                "file_hash": "c" * 64,
                "normalized_pdf_hash": "d" * 64,
                "version": 2,
            }
        )
    )

    updated = document.append(replacement)

    assert updated.versions == (first, replacement)
    assert updated.latest_version.version == 2


def test_document_rejects_duplicate_historical_hash() -> None:
    first = _version()
    document = Document.create(
        document_id=first.document_id,
        first_version=first,
    )
    duplicate = DocumentVersion(
        **(first.__dict__ | {"id": uuid4(), "version": 2})
    )

    with pytest.raises(ValueError, match="file hash"):
        document.append(duplicate)


def test_pdf_uses_original_object_as_normalized_pdf() -> None:
    version = _version()
    pdf_version = DocumentVersion(
        **(
            version.__dict__
            | {
                "name": "投标文件.pdf",
                "file_format": DocumentFormat.PDF,
                "normalized_pdf_url": version.file_url,
                "normalized_pdf_hash": version.file_hash,
            }
        )
    )

    assert pdf_version.normalized_pdf_url == pdf_version.file_url


def test_pdf_rejects_a_distinct_normalized_object() -> None:
    version = _version()

    with pytest.raises(ValueError, match="PDF source"):
        DocumentVersion(
            **(version.__dict__ | {"file_format": DocumentFormat.PDF})
        )
