"""PostgreSQL document-version locking, deduplication, and parse-source behavior."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bid_system.modules.documents.application.ports import PreparedDocumentVersion
from bid_system.modules.documents.domain.errors import DuplicateDocumentContentError
from bid_system.modules.documents.domain.models import DocumentFormat
from bid_system.modules.documents.infrastructure.repository import (
    SqlAlchemyDocumentRepository,
)

UPLOADED_AT = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)


def _prepared(
    *,
    document_id: UUID,
    file_hash: str = "a" * 64,
) -> PreparedDocumentVersion:
    return PreparedDocumentVersion(
        id=uuid4(),
        document_id=document_id,
        name="方案.pdf",
        file_url=f"minio://bucket/raw/{file_hash}",
        normalized_pdf_url=f"minio://bucket/raw/{file_hash}",
        file_format=DocumentFormat.PDF,
        file_hash=file_hash,
        normalized_pdf_hash=file_hash,
        uploaded_at=UPLOADED_AT,
        expires_at=None,
        page_count=10,
        parser_version="document-metadata-v1",
        parse_duration_ms=30,
    )


@pytest.mark.asyncio
async def test_create_and_append_allocate_contiguous_versions(
    db_session: AsyncSession,
) -> None:
    repository = SqlAlchemyDocumentRepository(db_session)
    document_id = uuid4()

    first = await repository.create(_prepared(document_id=document_id))
    second = await repository.append(
        document_id,
        _prepared(document_id=document_id, file_hash="b" * 64),
    )

    assert first.version == 1
    assert second.version == 2


@pytest.mark.asyncio
async def test_append_rejects_hash_from_any_historical_version(
    db_session: AsyncSession,
) -> None:
    repository = SqlAlchemyDocumentRepository(db_session)
    document_id = uuid4()
    await repository.create(_prepared(document_id=document_id))
    await repository.append(
        document_id,
        _prepared(document_id=document_id, file_hash="b" * 64),
    )

    with pytest.raises(DuplicateDocumentContentError):
        await repository.append(
            document_id,
            _prepared(document_id=document_id, file_hash="a" * 64),
        )


@pytest.mark.asyncio
async def test_append_uses_global_document_identity(db_session: AsyncSession) -> None:
    repository = SqlAlchemyDocumentRepository(db_session)
    document_id = uuid4()
    await repository.create(_prepared(document_id=document_id))

    version = await repository.append(
        document_id,
        _prepared(document_id=document_id, file_hash="b" * 64),
    )

    assert version.version == 2


@pytest.mark.asyncio
async def test_parse_source_returns_only_canonical_pdf_facts(
    db_session: AsyncSession,
) -> None:
    repository = SqlAlchemyDocumentRepository(db_session)
    document_id = uuid4()
    version = await repository.create(_prepared(document_id=document_id))

    source = await repository.get_parse_source(
        document_version_id=version.id,
    )

    assert source.document_version_id == version.id
    assert source.normalized_pdf_url == version.normalized_pdf_url
    assert source.normalized_pdf_hash == version.normalized_pdf_hash
    assert source.page_count == 10
