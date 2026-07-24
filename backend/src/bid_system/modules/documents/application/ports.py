"""Typed ports and boundary records for document ingestion."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from bid_system.modules.documents.domain.models import DocumentFormat, DocumentVersion


class UploadSource(Protocol):
    """One request-owned binary source read with an explicit maximum size."""

    filename: str

    async def read(self, size: int) -> bytes: ...


@dataclass(frozen=True)
class StagedUpload:
    """Bounded local source plus its streaming digest."""

    path: Path
    normalized_name: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ParsedDocument:
    """Canonical PDF metadata produced by the parser adapter."""

    normalized_pdf_path: Path
    normalized_pdf_hash: str
    page_count: int
    parser_version: str
    parse_duration_ms: int


@dataclass(frozen=True)
class PreparedDocumentVersion:
    """Version facts complete except for the repository-allocated sequence."""

    id: UUID
    document_id: UUID
    name: str
    file_url: str
    normalized_pdf_url: str
    file_format: DocumentFormat
    file_hash: str
    normalized_pdf_hash: str
    uploaded_at: datetime
    expires_at: datetime | None
    page_count: int
    parser_version: str
    parse_duration_ms: int

    def to_version(self, *, version: int) -> DocumentVersion:
        """Build the validated immutable domain record."""
        return DocumentVersion(
            id=self.id,
            document_id=self.document_id,
            name=self.name,
            file_url=self.file_url,
            normalized_pdf_url=self.normalized_pdf_url,
            file_format=self.file_format,
            file_hash=self.file_hash,
            normalized_pdf_hash=self.normalized_pdf_hash,
            version=version,
            uploaded_at=self.uploaded_at,
            expires_at=self.expires_at,
            page_count=self.page_count,
            parser_version=self.parser_version,
            parse_duration_ms=self.parse_duration_ms,
        )


class WorkspaceFactory(Protocol):
    def open(self) -> AbstractAsyncContextManager[Path]: ...


class UploadStager(Protocol):
    async def stage(self, source: UploadSource, workspace: Path) -> StagedUpload: ...


class FileTypeDetector(Protocol):
    async def detect(self, path: Path) -> DocumentFormat: ...


class FileSafetyScanner(Protocol):
    async def ensure_safe(self, path: Path, file_format: DocumentFormat) -> None: ...


class MetadataParser(Protocol):
    async def parse(
        self,
        source_path: Path,
        file_format: DocumentFormat,
        workspace: Path,
    ) -> ParsedDocument: ...


class DocumentBlobStore(Protocol):
    async def put(
        self,
        *,
        sha256: str,
        path: Path,
        content_type: str,
    ) -> str: ...


class DocumentVersionRepository(Protocol):
    async def create(self, prepared: PreparedDocumentVersion) -> DocumentVersion: ...

    async def append(
        self,
        document_id: UUID,
        prepared: PreparedDocumentVersion,
    ) -> DocumentVersion: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_id(self) -> UUID: ...
