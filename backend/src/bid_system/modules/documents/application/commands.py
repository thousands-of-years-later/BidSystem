"""Validated document-ingestion use-case inputs."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from bid_system.modules.documents.application.ports import UploadSource


@dataclass(frozen=True)
class UploadDocumentCommand:
    """Create a logical document or append one immutable version."""

    source: UploadSource
    expires_at: datetime | None
    document_id: UUID | None
