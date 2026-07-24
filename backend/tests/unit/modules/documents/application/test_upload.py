"""Upload use-case ordering and persistence behavior."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from bid_system.modules.documents.application.commands import UploadDocumentCommand
from bid_system.modules.documents.application.ports import (
    ParsedDocument,
    PreparedDocumentVersion,
    StagedUpload,
    UploadSource,
)
from bid_system.modules.documents.application.upload import UploadDocumentHandler
from bid_system.modules.documents.domain.errors import (
    InvalidDocumentError,
    PageLimitExceededError,
)
from bid_system.modules.documents.domain.models import DocumentFormat, DocumentVersion

DOCUMENT_ID = UUID("10000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("20000000-0000-0000-0000-000000000001")
UPLOADED_AT = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
SOURCE_HASH = "a" * 64
PDF_HASH = "b" * 64


class FakeSource:
    filename = "方案.docx"

    async def read(self, size: int) -> bytes:
        del size
        return b""


class FakeWorkspaceFactory:
    @asynccontextmanager
    async def open(self) -> AsyncIterator[Path]:
        yield Path("work")


class FakeStager:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def stage(self, source: UploadSource, workspace: Path) -> StagedUpload:
        del source, workspace
        self._calls.append("size")
        return StagedUpload(
            path=Path("work/source"),
            normalized_name="方案.docx",
            size_bytes=10,
            sha256=SOURCE_HASH,
        )


class FakeTypeDetector:
    def __init__(self, calls: list[str], file_format: DocumentFormat) -> None:
        self._calls = calls
        self._file_format = file_format

    async def detect(self, path: Path) -> DocumentFormat:
        del path
        self._calls.append("type")
        return self._file_format


class FakeSafetyScanner:
    def __init__(self, calls: list[str], error: Exception | None = None) -> None:
        self._calls = calls
        self._error = error

    async def ensure_safe(self, path: Path, file_format: DocumentFormat) -> None:
        del path, file_format
        self._calls.append("safety")
        if self._error is not None:
            raise self._error


class FakeMetadataParser:
    def __init__(
        self,
        calls: list[str],
        *,
        page_count: int = 8,
        pdf_hash: str = PDF_HASH,
    ) -> None:
        self._calls = calls
        self._page_count = page_count
        self._pdf_hash = pdf_hash

    async def parse(
        self,
        source_path: Path,
        file_format: DocumentFormat,
        workspace: Path,
    ) -> ParsedDocument:
        self._calls.append("metadata")
        pdf_path = (
            source_path
            if file_format is DocumentFormat.PDF
            else workspace / "normalized.pdf"
        )
        return ParsedDocument(
            normalized_pdf_path=pdf_path,
            normalized_pdf_hash=(
                SOURCE_HASH if file_format is DocumentFormat.PDF else self._pdf_hash
            ),
            page_count=self._page_count,
            parser_version="document-metadata-v1",
            parse_duration_ms=25,
        )


class FakeBlobStore:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.hashes: list[str] = []

    async def put(
        self,
        *,
        sha256: str,
        path: Path,
        content_type: str,
    ) -> str:
        del path, content_type
        self.calls.append("store")
        self.hashes.append(sha256)
        return f"minio://bid-system/{sha256}"


class FakeRepository:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls
        self.prepared: PreparedDocumentVersion | None = None

    async def create(self, prepared: PreparedDocumentVersion) -> DocumentVersion:
        self._calls.append("database")
        self.prepared = prepared
        return prepared.to_version(version=1)

    async def append(
        self,
        document_id: UUID,
        prepared: PreparedDocumentVersion,
    ) -> DocumentVersion:
        del document_id
        self._calls.append("database")
        self.prepared = prepared
        return prepared.to_version(version=2)


class FakeClock:
    def now(self) -> datetime:
        return UPLOADED_AT


class FakeIdGenerator:
    def __init__(self) -> None:
        self._values = iter((DOCUMENT_ID, VERSION_ID))

    def new_id(self) -> UUID:
        return next(self._values)


def _handler(
    *,
    calls: list[str],
    file_format: DocumentFormat,
    scanner_error: Exception | None = None,
    page_count: int = 8,
) -> tuple[UploadDocumentHandler, FakeBlobStore, FakeRepository]:
    blob_store = FakeBlobStore(calls)
    repository = FakeRepository(calls)
    return (
        UploadDocumentHandler(
            workspace_factory=FakeWorkspaceFactory(),
            stager=FakeStager(calls),
            type_detector=FakeTypeDetector(calls, file_format),
            safety_scanner=FakeSafetyScanner(calls, scanner_error),
            metadata_parser=FakeMetadataParser(calls, page_count=page_count),
            blob_store=blob_store,
            repository=repository,
            clock=FakeClock(),
            id_generator=FakeIdGenerator(),
        ),
        blob_store,
        repository,
    )


@pytest.mark.asyncio
async def test_office_upload_follows_required_order_and_stores_both_objects() -> None:
    calls: list[str] = []
    handler, blob_store, repository = _handler(
        calls=calls,
        file_format=DocumentFormat.DOCX,
    )

    result = await handler.handle(
        UploadDocumentCommand(
            source=FakeSource(),
            expires_at=None,
            document_id=None,
        )
    )

    assert calls == ["size", "type", "safety", "metadata", "store", "store", "database"]
    assert blob_store.hashes == [SOURCE_HASH, PDF_HASH]
    assert result.version == 1
    assert repository.prepared is not None
    assert repository.prepared.normalized_pdf_url.endswith(PDF_HASH)


@pytest.mark.asyncio
async def test_pdf_upload_reuses_original_object_as_normalized_pdf() -> None:
    calls: list[str] = []
    handler, blob_store, repository = _handler(
        calls=calls,
        file_format=DocumentFormat.PDF,
    )

    await handler.handle(
        UploadDocumentCommand(
            source=FakeSource(),
            expires_at=None,
            document_id=None,
        )
    )

    assert blob_store.hashes == [SOURCE_HASH]
    assert repository.prepared is not None
    assert repository.prepared.file_url == repository.prepared.normalized_pdf_url


@pytest.mark.asyncio
async def test_safety_failure_stops_before_metadata_and_persistence() -> None:
    calls: list[str] = []
    handler, _, _ = _handler(
        calls=calls,
        file_format=DocumentFormat.DOCX,
        scanner_error=RuntimeError("unsafe"),
    )

    with pytest.raises(RuntimeError, match="unsafe"):
        await handler.handle(
            UploadDocumentCommand(
                source=FakeSource(),
                expires_at=None,
                document_id=None,
            )
        )

    assert calls == ["size", "type", "safety"]


@pytest.mark.asyncio
async def test_page_limit_failure_stops_before_object_storage() -> None:
    calls: list[str] = []
    handler, _, _ = _handler(
        calls=calls,
        file_format=DocumentFormat.PPTX,
        page_count=501,
    )

    with pytest.raises(PageLimitExceededError):
        await handler.handle(
            UploadDocumentCommand(
                source=FakeSource(),
                expires_at=None,
                document_id=None,
            )
        )

    assert calls == ["size", "type", "safety", "metadata"]


@pytest.mark.asyncio
async def test_zero_page_document_stops_before_object_storage() -> None:
    calls: list[str] = []
    handler, _, _ = _handler(
        calls=calls,
        file_format=DocumentFormat.PDF,
        page_count=0,
    )

    with pytest.raises(InvalidDocumentError):
        await handler.handle(
            UploadDocumentCommand(
                source=FakeSource(),
                expires_at=None,
                document_id=None,
            )
        )

    assert calls == ["size", "type", "safety", "metadata"]


@pytest.mark.asyncio
async def test_existing_document_uses_append_repository_path() -> None:
    calls: list[str] = []
    handler, _, _ = _handler(calls=calls, file_format=DocumentFormat.DOCX)

    result = await handler.handle(
        UploadDocumentCommand(
            source=FakeSource(),
            expires_at=None,
            document_id=DOCUMENT_ID,
        )
    )

    assert result.version == 2
