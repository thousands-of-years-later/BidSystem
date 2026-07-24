"""Stable document query projections exposed across module boundaries."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DocumentParseSource:
    """Canonical PDF facts required by downstream parsing workers."""

    document_version_id: UUID
    normalized_pdf_url: str
    normalized_pdf_hash: str
    page_count: int
    parser_version: str
