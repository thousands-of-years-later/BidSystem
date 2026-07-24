"""Authenticated multipart protocol mapping for document ingestion."""

from datetime import datetime
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict
from starlette.datastructures import UploadFile as StarletteUploadFile

from bid_system.entrypoints.api.dependencies import (
    RequestContext,
    get_current_principal,
    get_database_resource,
    get_minio_resource,
    get_request_context,
    get_settings,
)
from bid_system.entrypoints.api.responses import success_response
from bid_system.modules.documents.application.commands import UploadDocumentCommand
from bid_system.modules.documents.domain.errors import InvalidDocumentUploadRequestError
from bid_system.modules.documents.domain.models import DocumentFormat, DocumentVersion
from bid_system.modules.identity.domain.access import PermissionCode
from bid_system.platform.security.authentication import AuthenticatedPrincipal
from bid_system.platform.security.authorization import PermissionEvaluator
from bid_system.shared.contracts.api import SuccessResponse

router = APIRouter(prefix="/documents")
ALLOWED_MULTIPART_FIELDS = frozenset({"file", "expires_at"})
MAX_MULTIPART_FILES = 2
MAX_MULTIPART_FIELDS = 2


class DocumentUploadUseCase(Protocol):
    async def handle(self, command: UploadDocumentCommand) -> DocumentVersion: ...


class FastApiUploadSource:
    """Adapt FastAPI's nullable filename contract to the application port."""

    def __init__(self, upload: UploadFile) -> None:
        if upload.filename is None:
            raise InvalidDocumentUploadRequestError(public_message="文件名不能为空")
        self.filename = upload.filename
        self._upload = upload

    async def read(self, size: int) -> bytes:
        return await self._upload.read(size)


class DocumentVersionResponse(BaseModel):
    """Complete non-sensitive metadata for one stored source version."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", frozen=True)

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


def get_document_upload_handler(request: Request) -> DocumentUploadUseCase:
    """Construct the use case from application-scoped resources."""
    from bid_system.bootstrap.dependencies import build_document_upload_handler
    from bid_system.platform.database.engine import DatabaseResource
    from bid_system.platform.object_store.client import MinioResource

    database = get_database_resource(request)
    minio = get_minio_resource(request)
    if not isinstance(database, DatabaseResource):
        raise RuntimeError("Initialized database resource has an unsupported type")
    if not isinstance(minio, MinioResource):
        raise RuntimeError("Initialized MinIO resource has an unsupported type")
    return build_document_upload_handler(
        database=database,
        minio=minio,
        settings=get_settings(request).documents,
    )


async def enforce_single_upload_file(request: Request) -> None:
    """Reject extra file parts and undeclared multipart fields."""
    try:
        form = await request.form(
            max_files=MAX_MULTIPART_FILES,
            max_fields=MAX_MULTIPART_FIELDS,
        )
    except Exception as error:
        # WHY: multipart parser diagnostics can echo attacker-controlled field names.
        raise InvalidDocumentUploadRequestError from error
    items = form.multi_items()
    files = [value for _, value in items if isinstance(value, StarletteUploadFile)]
    field_names = {name for name, _ in items}
    if len(files) != 1 or not field_names <= ALLOWED_MULTIPART_FIELDS:
        raise InvalidDocumentUploadRequestError
    if sum(1 for name, _ in items if name == "file") != 1:
        raise InvalidDocumentUploadRequestError
    if sum(1 for name, _ in items if name == "expires_at") > 1:
        raise InvalidDocumentUploadRequestError


def _require_permission(
    principal: AuthenticatedPrincipal,
    permission: PermissionCode,
) -> None:
    PermissionEvaluator.require(
        PermissionEvaluator.evaluate(
            principal,
            required_permissions=frozenset({permission.value}),
            tenant_id=principal.tenant_id,
        )
    )


async def _upload(
    *,
    document_id: UUID | None,
    file: UploadFile,
    expires_at: datetime | None,
    principal: AuthenticatedPrincipal,
    context: RequestContext,
    handler: DocumentUploadUseCase,
    permission: PermissionCode,
) -> SuccessResponse[DocumentVersionResponse]:
    _require_permission(principal, permission)
    version = await handler.handle(
        UploadDocumentCommand(
            source=FastApiUploadSource(file),
            expires_at=expires_at,
            document_id=document_id,
        )
    )
    return success_response(
        data=DocumentVersionResponse.model_validate(version),
        request_id=context.request_id,
    )


@router.post(
    "",
    name="documents_create",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[DocumentVersionResponse],
    dependencies=[Depends(enforce_single_upload_file)],
)
async def create_document(
    file: Annotated[UploadFile, File()],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    handler: Annotated[DocumentUploadUseCase, Depends(get_document_upload_handler)],
    expires_at: Annotated[datetime | None, Form()] = None,
) -> SuccessResponse[DocumentVersionResponse]:
    """Validate, canonicalize, and store the first immutable document version."""
    return await _upload(
        document_id=None,
        file=file,
        expires_at=expires_at,
        principal=principal,
        context=context,
        handler=handler,
        permission=PermissionCode.CONTENT_UPLOAD,
    )


@router.post(
    "/{document_id}/versions",
    name="documents_create_version",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[DocumentVersionResponse],
    dependencies=[Depends(enforce_single_upload_file)],
)
async def create_document_version(
    document_id: UUID,
    file: Annotated[UploadFile, File()],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    handler: Annotated[DocumentUploadUseCase, Depends(get_document_upload_handler)],
    expires_at: Annotated[datetime | None, Form()] = None,
) -> SuccessResponse[DocumentVersionResponse]:
    """Append a distinct immutable version to a globally shared document."""
    return await _upload(
        document_id=document_id,
        file=file,
        expires_at=expires_at,
        principal=principal,
        context=context,
        handler=handler,
        permission=PermissionCode.CONTENT_MODIFY,
    )
