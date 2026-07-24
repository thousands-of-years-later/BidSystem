"""PostgreSQL repository for append-only document versions."""

from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bid_system.modules.documents.application.dto import DocumentParseSource
from bid_system.modules.documents.application.ports import PreparedDocumentVersion
from bid_system.modules.documents.domain.errors import DuplicateDocumentContentError
from bid_system.modules.documents.domain.models import DocumentVersion
from bid_system.modules.documents.infrastructure.models import (
    DocumentModel,
    DocumentVersionModel,
)
from bid_system.platform.database.engine import DatabaseResource
from bid_system.shared.contracts.errors import (
    BusinessConflictError,
    ResourceNotFoundError,
)

DUPLICATE_CONTENT_CONSTRAINT = "uq_document_version_document_file_hash"
VERSION_SEQUENCE_CONSTRAINT = "uq_document_version_document_version_sequence"


class SqlAlchemyDocumentRepository:
    """Persist document facts inside the caller-owned short transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, prepared: PreparedDocumentVersion) -> DocumentVersion:
        version = prepared.to_version(version=1)
        self._session.add(
            DocumentModel(
                id=version.document_id,
                created_at=version.uploaded_at,
            )
        )
        self._session.add(self._to_model(version))
        try:
            await self._session.flush()
        except IntegrityError as error:
            self._raise_integrity_error(error)
        return version

    async def append(
        self,
        document_id: UUID,
        prepared: PreparedDocumentVersion,
    ) -> DocumentVersion:
        if prepared.document_id != document_id:
            raise ValueError("prepared version does not match requested document")
        document_result = await self._session.execute(
            select(DocumentModel)
            .where(DocumentModel.id == document_id)
            .with_for_update()
        )
        if document_result.scalar_one_or_none() is None:
            raise ResourceNotFoundError
        duplicate_result = await self._session.execute(
            select(DocumentVersionModel.id)
            .where(
                DocumentVersionModel.document_id == document_id,
                DocumentVersionModel.file_hash == prepared.file_hash,
            )
            .limit(1)
        )
        if duplicate_result.scalar_one_or_none() is not None:
            raise DuplicateDocumentContentError
        version_result = await self._session.execute(
            select(func.max(DocumentVersionModel.version)).where(
                DocumentVersionModel.document_id == document_id
            )
        )
        latest_version = version_result.scalar_one()
        if latest_version is None:
            raise RuntimeError("logical document has no first version")
        version = prepared.to_version(version=latest_version + 1)
        self._session.add(self._to_model(version))
        try:
            await self._session.flush()
        except IntegrityError as error:
            self._raise_integrity_error(error)
        return version

    async def get_parse_source(
        self,
        *,
        document_version_id: UUID,
    ) -> DocumentParseSource:
        result = await self._session.execute(
            select(DocumentVersionModel).where(
                DocumentVersionModel.id == document_version_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ResourceNotFoundError
        return DocumentParseSource(
            document_version_id=model.id,
            normalized_pdf_url=model.normalized_pdf_url,
            normalized_pdf_hash=model.normalized_pdf_hash,
            page_count=model.page_count,
            parser_version=model.parser_version,
        )

    @staticmethod
    def _to_model(version: DocumentVersion) -> DocumentVersionModel:
        return DocumentVersionModel(
            id=version.id,
            document_id=version.document_id,
            name=version.name,
            file_url=version.file_url,
            normalized_pdf_url=version.normalized_pdf_url,
            file_format=version.file_format,
            file_hash=version.file_hash,
            normalized_pdf_hash=version.normalized_pdf_hash,
            version=version.version,
            uploaded_at=version.uploaded_at,
            expires_at=version.expires_at,
            page_count=version.page_count,
            parser_version=version.parser_version,
            parse_duration_ms=version.parse_duration_ms,
        )

    @staticmethod
    def _raise_integrity_error(error: IntegrityError) -> None:
        if isinstance(error.orig, UniqueViolation):
            constraint_name = error.orig.diag.constraint_name
            if constraint_name == DUPLICATE_CONTENT_CONSTRAINT:
                raise DuplicateDocumentContentError from error
            if constraint_name == VERSION_SEQUENCE_CONSTRAINT:
                raise BusinessConflictError(
                    public_message="文档版本发生并发冲突"
                ) from error
            raise BusinessConflictError from error
        raise error


class TransactionalDocumentRepository:
    """Open a short database transaction only after all object writes complete."""

    def __init__(self, resource: DatabaseResource) -> None:
        self._resource = resource

    async def create(self, prepared: PreparedDocumentVersion) -> DocumentVersion:
        async with self._resource.transaction() as transaction:
            version = await SqlAlchemyDocumentRepository(transaction.session).create(
                prepared
            )
        return version

    async def append(
        self,
        document_id: UUID,
        prepared: PreparedDocumentVersion,
    ) -> DocumentVersion:
        async with self._resource.transaction() as transaction:
            version = await SqlAlchemyDocumentRepository(transaction.session).append(
                document_id,
                prepared,
            )
        return version

    async def get_parse_source(
        self,
        *,
        document_version_id: UUID,
    ) -> DocumentParseSource:
        async with self._resource.transaction() as transaction:
            source = await SqlAlchemyDocumentRepository(
                transaction.session
            ).get_parse_source(
                document_version_id=document_version_id,
            )
        return source
