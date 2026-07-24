"""Canonical PDF lookup for downstream parsing workflows."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from bid_system.modules.documents.application.dto import DocumentParseSource


class DocumentParseSourceReader(Protocol):
    async def get_parse_source(
        self,
        *,
        document_version_id: UUID,
    ) -> DocumentParseSource: ...


@dataclass(frozen=True)
class GetDocumentParseSourceQuery:
    document_version_id: UUID


class GetDocumentParseSourceHandler:
    """Resolve a globally visible version to its durable normalized PDF."""

    def __init__(self, reader: DocumentParseSourceReader) -> None:
        self._reader = reader

    async def handle(self, query: GetDocumentParseSourceQuery) -> DocumentParseSource:
        return await self._reader.get_parse_source(
            document_version_id=query.document_version_id,
        )
