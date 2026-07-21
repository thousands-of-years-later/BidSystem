"""Stable HTTP exception envelope tests."""

import logging
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import AfterValidator, BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import Message, Receive, Scope, Send

from bid_system.entrypoints.api.app import create_app
from bid_system.entrypoints.api.dependencies import RequestContext
from bid_system.entrypoints.api.exception_handlers import UnhandledExceptionMiddleware
from bid_system.platform.config import AppSettings
from bid_system.shared.contracts.errors import (
    ApplicationError,
    AuthenticationError,
    BusinessConflictError,
    DomainError,
    ExternalServiceError,
    PermissionDeniedError,
    ResourceNotFoundError,
    StateTransitionError,
)


@dataclass
class FakeResource:
    client: str = "fake"

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


def make_app() -> FastAPI:
    settings = AppSettings(
        APP_ENV="test",
        DATABASE_URL="postgresql+psycopg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="access",
        MINIO_SECRET_KEY="secret",
        MINIO_BUCKET="bucket",
    )
    return create_app(settings=settings, container_factory=FakeContainer)


def test_validation_error_uses_stable_envelope() -> None:
    app = make_app()

    @app.get("/number/{value}")
    async def number(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/number/not-an-integer")

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "请求参数不合法"
    assert body["details"][0]["location"] == ["path", "value"]
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_validation_error_does_not_expose_input_or_validator_context() -> None:
    app = make_app()

    def reject_secret(value: str) -> str:
        raise ValueError(f"invalid credential: {value}")

    class CredentialPayload(BaseModel):
        credential: Annotated[str, AfterValidator(reject_secret)]

    @app.post("/credentials")
    async def credentials(payload: CredentialPayload) -> None:
        del payload

    with TestClient(app) as client:
        response = client.post("/credentials", json={"credential": "private-token"})

    assert response.status_code == 422
    assert "private-token" not in response.text
    assert "invalid credential" not in response.text


def test_http_exception_uses_stable_envelope() -> None:
    app = make_app()

    with TestClient(app) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "资源不存在",
        "details": [],
        "request_id": response.headers["X-Request-ID"],
    }


def test_http_exception_hides_detail_and_preserves_safe_protocol_headers() -> None:
    app = make_app()

    @app.get("/protected")
    async def protected() -> None:
        raise HTTPException(
            status_code=401,
            detail="private-auth-diagnostic",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with TestClient(app) as client:
        response = client.get("/protected")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "private-auth-diagnostic" not in response.text


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (ResourceNotFoundError(), 404, "NOT_FOUND"),
        (BusinessConflictError(), 409, "CONFLICT"),
        (StateTransitionError(), 409, "INVALID_STATE_TRANSITION"),
        (AuthenticationError(), 401, "AUTHENTICATION_REQUIRED"),
        (PermissionDeniedError(), 403, "PERMISSION_DENIED"),
        (ExternalServiceError(), 503, "EXTERNAL_SERVICE_UNAVAILABLE"),
        (ApplicationError(), 400, "APPLICATION_ERROR"),
        (DomainError(), 422, "DOMAIN_ERROR"),
    ],
)
def test_business_exceptions_use_central_http_mapping(
    error: ApplicationError | DomainError,
    expected_status: int,
    expected_code: str,
) -> None:
    app = make_app()

    @app.get("/business-error")
    async def business_error() -> None:
        raise error

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/business-error")

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_database_exception_is_sanitized_and_keeps_request_id() -> None:
    app = make_app()

    @app.get("/database-error")
    async def database_error() -> None:
        raise SQLAlchemyError("SELECT password FROM users WHERE token='private-token'")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/database-error")

    assert response.status_code == 503
    assert response.json() == {
        "code": "DATABASE_UNAVAILABLE",
        "message": "数据库服务暂时不可用",
        "details": [],
        "request_id": response.headers["X-Request-ID"],
    }
    assert "SELECT" not in response.text
    assert "private-token" not in response.text


def test_unknown_exception_is_hidden_and_keeps_correlation_id() -> None:
    app = make_app()

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("internal-secret-marker")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/explode")

    body = response.json()
    assert response.status_code == 500
    assert body == {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "服务器内部错误",
        "details": [],
        "request_id": response.headers["X-Request-ID"],
    }
    assert "internal-secret-marker" not in response.text


@pytest.mark.asyncio
async def test_unknown_exception_log_keeps_traceback_without_exception_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class SensitiveFailure(RuntimeError):
        pass

    async def failing_app(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive, send
        sensitive_diagnostic = "token=" + "private-token"
        raise SensitiveFailure(sensitive_diagnostic)

    middleware = UnhandledExceptionMiddleware(failing_app)
    context = RequestContext(
        request_id="request-1",
        trace_id="trace-1",
        user_id=None,
        tenant_id=None,
        method="GET",
        path="/logged-explosion",
        client_ip=None,
        started_at=datetime.now(UTC),
    )
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/logged-explosion",
        "headers": [],
        "state": {"request_context": context},
    }
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    caplog.set_level(logging.ERROR, logger="bid_system.api.errors")
    await middleware(scope, receive, send)

    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 500
    record = next(
        item for item in caplog.records if item.getMessage() == "unhandled_request_exception"
    )
    assert record.exc_info is not None
    assert record.exc_info[2] is not None
    assert "failing_app" in "".join(traceback.format_tb(record.exc_info[2]))
    assert "SensitiveFailure" in caplog.text
    assert "private-token" not in caplog.text


@pytest.mark.asyncio
async def test_unknown_exception_after_response_start_is_reraised() -> None:
    async def broken_app(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("stream failed")

    middleware = UnhandledExceptionMiddleware(broken_app)
    context = RequestContext(
        request_id="request-1",
        trace_id="trace-1",
        user_id=None,
        tenant_id=None,
        method="GET",
        path="/stream",
        client_ip=None,
        started_at=datetime.now(UTC),
    )
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/stream",
        "headers": [],
        "state": {"request_context": context},
    }
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    with pytest.raises(RuntimeError, match="stream failed"):
        await middleware(scope, receive, send)

    assert [message["type"] for message in messages] == ["http.response.start"]
