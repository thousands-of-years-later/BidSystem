"""SQLAlchemy models exclusively owned by the documents module."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from bid_system.modules.documents.domain.models import DocumentFormat
from bid_system.platform.database.models import OrmBase

DOCUMENTS_SCHEMA = "documents"
DOCUMENT_NAME_LENGTH = 255
SHA256_LENGTH = 64
PARSER_VERSION_LENGTH = 100


def _format_values(enum_type: type[DocumentFormat]) -> list[str]:
    return [member.value for member in enum_type]


class DocumentModel(OrmBase):
    """Globally visible logical document whose versions are append-only."""

    __tablename__ = "document"
    __table_args__ = ({"schema": DOCUMENTS_SCHEMA},)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentVersionModel(OrmBase):
    """Immutable source and canonical-PDF metadata for one document version."""

    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="document_version_sequence"),
        UniqueConstraint("document_id", "file_hash", name="document_file_hash"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "page_count BETWEEN 1 AND 500",
            name="page_count_supported",
        ),
        CheckConstraint(
            "parse_duration_ms >= 0",
            name="parse_duration_non_negative",
        ),
        {"schema": DOCUMENTS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{DOCUMENTS_SCHEMA}.document.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(DOCUMENT_NAME_LENGTH), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_pdf_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[DocumentFormat] = mapped_column(
        Enum(
            DocumentFormat,
            name="document_format",
            native_enum=False,
            values_callable=_format_values,
        ),
        nullable=False,
    )
    file_hash: Mapped[str] = mapped_column(String(SHA256_LENGTH), nullable=False)
    normalized_pdf_hash: Mapped[str] = mapped_column(String(SHA256_LENGTH), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(PARSER_VERSION_LENGTH), nullable=False)
    parse_duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
