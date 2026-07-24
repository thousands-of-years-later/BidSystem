"""Authenticated one-file document upload HTTP contract."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from bid_system.entrypoints.api.app import create_app
from bid_system.entrypoints.api.dependencies import get_current_principal
from bid_system.modules.documents.application.commands import UploadDocumentCommand
from bid_system.modules.documents.domain.errors import (
    DuplicateDocumentContentError,
    EncryptedDocumentError,
    FileSizeLimitExceededError,
    PageLimitExceededError,
    UnsupportedDocumentTypeError,
)
from bid_system.modules.documents.domain.models import DocumentFormat, DocumentVersion
from bid_system.modules.documents.interfaces.http import (
    get_document_upload_handler,
)
from bid_system.platform.config import AppSettings
from bid_system.platform.security.authentication import AuthenticatedPrincipal

DOCUMENT_ID = UUID("10000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("20000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)


@dataclass
class FakeResource:
    async def probe(self) -> None:
        return None

    async def close(self) -> None:
        return None


@dataclass
class FakeContainer:
    settings: AppSettings
    database: FakeResource = field(default_factory=FakeResource)
    redis: FakeResource = field(default_factory=FakeResource)
    minio: FakeResource = field(default_factory=FakeResource)

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None


class RecordingHandler:
    def __init__(self) -> None:
        self.commands: list[UploadDocumentCommand] = []

    async def handle(self, command: UploadDocumentCommand) -> DocumentVersion:
        self.commands.append(command)
        document_id = command.document_id or DOCUMENT_ID
        version = 1 if command.document_id is None else 2
        return DocumentVersion(
            id=VERSION_ID,
            document_id=document_id,
            name="方案.pdf",
            file_url="minio://bucket/raw",
            normalized_pdf_url="minio://bucket/raw",
            file_format=DocumentFormat.PDF,
            file_hash="a" * 64,
            normalized_pdf_hash="a" * 64,
            version=version,
            uploaded_at=NOW,
            expires_at=command.expires_at,
            page_count=3,
            parser_version="document-metadata-v1",
            parse_duration_ms=20,
        )


class FailingHandler:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def handle(self, command: UploadDocumentCommand) -> DocumentVersion:
        del command
        raise self._error


def _settings() -> AppSettings:
    return AppSettings(
        APP_ENV="test",
        DATABASE_URL="postgresql+psycopg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="access",
        MINIO_SECRET_KEY="secret",
        MINIO_BUCKET="bucket",
    )


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id="manager",
        tenant_id="default",
        session_id="session",
        roles=frozenset({"manager"}),
        permissions=frozenset({"content.upload", "content.modify"}),
        active=True,
    )


def _client(
    handler: RecordingHandler | FailingHandler,
    *,
    principal: AuthenticatedPrincipal | None = None,
) -> TestClient:
    app = create_app(settings=_settings(), container_factory=FakeContainer)
    resolved_principal = principal or _principal()
    app.dependency_overrides[get_current_principal] = lambda: resolved_principal
    app.dependency_overrides[get_document_upload_handler] = lambda: handler
    return TestClient(app)


def test_create_document_accepts_exactly_one_file_and_optional_expiration() -> None:
    handler = RecordingHandler()

    with _client(handler) as client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("方案.pdf", b"%PDF-source", "text/plain")},
            data={"expires_at": "2027-01-01T00:00:00+00:00"},
        )

    assert response.status_code == 201
    assert response.json()["data"]["version"] == 1
    assert response.json()["data"]["parse_duration_ms"] == 20
    assert len(handler.commands) == 1
    assert handler.commands[0].expires_at == datetime(2027, 1, 1, tzinfo=UTC)


def test_upload_new_version_uses_path_document_id() -> None:
    handler = RecordingHandler()

    with _client(handler) as client:
        response = client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/versions",
            files={"file": ("方案.pdf", b"%PDF-source", "application/pdf")},
        )

    assert response.status_code == 201
    assert response.json()["data"]["version"] == 2
    assert handler.commands[0].document_id == DOCUMENT_ID


def test_employee_cannot_upload_or_create_versions() -> None:
    handler = RecordingHandler()
    employee = AuthenticatedPrincipal(
        user_id="employee",
        tenant_id="default",
        session_id="session",
        roles=frozenset({"employee"}),
        permissions=frozenset(),
        active=True,
    )

    with _client(handler, principal=employee) as client:
        create_response = client.post(
            "/api/v1/documents",
            files={"file": ("one.pdf", b"one", "application/pdf")},
        )
        update_response = client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/versions",
            files={"file": ("two.pdf", b"two", "application/pdf")},
        )

    assert create_response.status_code == 403
    assert update_response.status_code == 403
    assert handler.commands == []


def test_upload_rejects_more_than_one_file_without_calling_handler() -> None:
    handler = RecordingHandler()

    with _client(handler) as client:
        response = client.post(
            "/api/v1/documents",
            files=[
                ("file", ("one.pdf", b"one", "application/pdf")),
                ("file", ("two.pdf", b"two", "application/pdf")),
            ],
        )

    assert response.status_code == 422
    assert handler.commands == []


def test_upload_rejects_unknown_multipart_field() -> None:
    handler = RecordingHandler()

    with _client(handler) as client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("one.pdf", b"one", "application/pdf")},
            data={"unknown": "value"},
        )

    assert response.status_code == 422
    assert handler.commands == []


def test_openapi_exposes_authenticated_multipart_document_routes() -> None:
    handler = RecordingHandler()

    with _client(handler) as client:
        schema = client.get("/openapi.json").json()

    create_operation = schema["paths"]["/api/v1/documents"]["post"]
    version_operation = schema["paths"][
        "/api/v1/documents/{document_id}/versions"
    ]["post"]
    assert create_operation["security"] == [{"HTTPBearer": []}]
    assert version_operation["security"] == [{"HTTPBearer": []}]
    assert "multipart/form-data" in create_operation["requestBody"]["content"]


def test_document_failures_have_stable_http_status_and_code() -> None:
    cases = (
        (FileSizeLimitExceededError(), 413, "FILE_TOO_LARGE"),
        (UnsupportedDocumentTypeError(), 415, "UNSUPPORTED_DOCUMENT_TYPE"),
        (EncryptedDocumentError(), 422, "ENCRYPTED_DOCUMENT"),
        (PageLimitExceededError(), 422, "PAGE_LIMIT_EXCEEDED"),
        (DuplicateDocumentContentError(), 409, "DUPLICATE_DOCUMENT_CONTENT"),
    )

    for error, expected_status, expected_code in cases:
        with _client(FailingHandler(error)) as client:
            response = client.post(
                "/api/v1/documents",
                files={"file": ("方案.pdf", b"%PDF-source", "application/pdf")},
            )

        assert response.status_code == expected_status
        assert response.json()["code"] == expected_code
