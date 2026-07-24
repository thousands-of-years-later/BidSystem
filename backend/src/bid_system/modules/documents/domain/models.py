"""Pure document aggregate and immutable source-version facts."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from string import hexdigits
from uuid import UUID

MAX_DOCUMENT_PAGES = 500
SHA256_HEX_LENGTH = 64


class DocumentFormat(StrEnum):
    """Source formats accepted by the ingestion boundary."""

    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"


def _is_sha256(value: str) -> bool:
    return len(value) == SHA256_HEX_LENGTH and all(
        character in hexdigits for character in value
    )


@dataclass(frozen=True)
class DocumentVersion:
    """One immutable source upload and its canonical PDF parsing source."""

    id: UUID
    document_id: UUID
    name: str
    file_url: str
    normalized_pdf_url: str
    file_format: DocumentFormat
    file_hash: str
    normalized_pdf_hash: str
    version: int
    uploaded_at: datetime
    expires_at: datetime | None
    page_count: int
    parser_version: str
    parse_duration_ms: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("document name must not be blank")
        if not self.file_url.strip() or not self.normalized_pdf_url.strip():
            raise ValueError("document object URLs must not be blank")
        if not _is_sha256(self.file_hash) or not _is_sha256(self.normalized_pdf_hash):
            raise ValueError("document hashes must be SHA-256 hex digests")
        if self.version < 1:
            raise ValueError("document version must be positive")
        if not 1 <= self.page_count <= MAX_DOCUMENT_PAGES:
            raise ValueError("document page count is outside the supported boundary")
        if not self.parser_version.strip():
            raise ValueError("parser version must not be blank")
        if self.parse_duration_ms < 0:
            raise ValueError("parse duration must not be negative")
        if self.uploaded_at.tzinfo is None or self.uploaded_at.utcoffset() is None:
            raise ValueError("upload time must be timezone-aware")
        if (
            self.expires_at is not None
            and (self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None)
        ):
            raise ValueError("expiration time must be timezone-aware")
        if self.file_format is DocumentFormat.PDF and (
            self.normalized_pdf_url != self.file_url
            or self.normalized_pdf_hash != self.file_hash
        ):
            # WHY: a PDF already is the canonical parsing source; a second object would
            # waste storage and could later diverge from the original evidence.
            raise ValueError("PDF source must be its own normalized PDF")


@dataclass(frozen=True)
class Document:
    """Globally visible logical document with an append-only version history."""

    id: UUID
    versions: tuple[DocumentVersion, ...]

    def __post_init__(self) -> None:
        if not self.versions:
            raise ValueError("document must contain at least one version")
        expected_version = 1
        hashes: set[str] = set()
        for version in self.versions:
            if version.document_id != self.id:
                raise ValueError("document version does not match its document")
            if version.version != expected_version:
                raise ValueError("document versions must be contiguous and start at one")
            if version.file_hash in hashes:
                raise ValueError("document file hash already exists in version history")
            hashes.add(version.file_hash)
            expected_version += 1

    @classmethod
    def create(
        cls,
        *,
        document_id: UUID,
        first_version: DocumentVersion,
    ) -> "Document":
        """Create a logical document from its required first version."""
        return cls(id=document_id, versions=(first_version,))

    @property
    def latest_version(self) -> DocumentVersion:
        """Return the current immutable version."""
        return self.versions[-1]

    def append(self, version: DocumentVersion) -> "Document":
        """Return a new aggregate containing exactly the next distinct version."""
        return Document(
            id=self.id,
            versions=(*self.versions, version),
        )
