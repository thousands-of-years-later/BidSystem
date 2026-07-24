"""Ordered document upload, inspection, canonicalization, and persistence."""

from bid_system.modules.documents.application.commands import UploadDocumentCommand
from bid_system.modules.documents.application.ports import (
    Clock,
    DocumentBlobStore,
    DocumentVersionRepository,
    FileSafetyScanner,
    FileTypeDetector,
    IdGenerator,
    MetadataParser,
    PreparedDocumentVersion,
    UploadStager,
    WorkspaceFactory,
)
from bid_system.modules.documents.domain.errors import (
    InvalidDocumentError,
    PageLimitExceededError,
)
from bid_system.modules.documents.domain.models import (
    MAX_DOCUMENT_PAGES,
    DocumentFormat,
    DocumentVersion,
)

CANONICAL_MIME_TYPES: dict[DocumentFormat, str] = {
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    DocumentFormat.PPTX: (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
}


class UploadDocumentHandler:
    """Run the security-sensitive ingestion sequence exactly once."""

    def __init__(
        self,
        *,
        workspace_factory: WorkspaceFactory,
        stager: UploadStager,
        type_detector: FileTypeDetector,
        safety_scanner: FileSafetyScanner,
        metadata_parser: MetadataParser,
        blob_store: DocumentBlobStore,
        repository: DocumentVersionRepository,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._workspace_factory = workspace_factory
        self._stager = stager
        self._type_detector = type_detector
        self._safety_scanner = safety_scanner
        self._metadata_parser = metadata_parser
        self._blob_store = blob_store
        self._repository = repository
        self._clock = clock
        self._id_generator = id_generator

    async def handle(self, command: UploadDocumentCommand) -> DocumentVersion:
        async with self._workspace_factory.open() as workspace:
            staged = await self._stager.stage(command.source, workspace)
            file_format = await self._type_detector.detect(staged.path)
            await self._safety_scanner.ensure_safe(staged.path, file_format)
            parsed = await self._metadata_parser.parse(
                staged.path,
                file_format,
                workspace,
            )
            if parsed.page_count > MAX_DOCUMENT_PAGES:
                raise PageLimitExceededError
            if parsed.page_count < 1:
                raise InvalidDocumentError(public_message="文件不包含可解析页面")

            source_url = await self._blob_store.put(
                sha256=staged.sha256,
                path=staged.path,
                content_type=CANONICAL_MIME_TYPES[file_format],
            )
            if file_format is DocumentFormat.PDF:
                normalized_pdf_url = source_url
            else:
                normalized_pdf_url = await self._blob_store.put(
                    sha256=parsed.normalized_pdf_hash,
                    path=parsed.normalized_pdf_path,
                    content_type=CANONICAL_MIME_TYPES[DocumentFormat.PDF],
                )

            document_id = command.document_id or self._id_generator.new_id()
            prepared = PreparedDocumentVersion(
                id=self._id_generator.new_id(),
                document_id=document_id,
                name=staged.normalized_name,
                file_url=source_url,
                normalized_pdf_url=normalized_pdf_url,
                file_format=file_format,
                file_hash=staged.sha256,
                normalized_pdf_hash=parsed.normalized_pdf_hash,
                uploaded_at=self._clock.now(),
                expires_at=command.expires_at,
                page_count=parsed.page_count,
                parser_version=parsed.parser_version,
                parse_duration_ms=parsed.parse_duration_ms,
            )
            if command.document_id is None:
                return await self._repository.create(prepared)
            return await self._repository.append(command.document_id, prepared)
