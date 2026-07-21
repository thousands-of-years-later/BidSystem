"""Request context middleware behavior tests."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.testclient import TestClient

from bid_system.entrypoints.api.app import create_app
from bid_system.entrypoints.api.dependencies import RequestContext, get_request_context
from bid_system.platform.config import AppSettings


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


def make_settings() -> AppSettings:
    return AppSettings(
        APP_ENV="test",
        DATABASE_URL="postgresql+psycopg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="access",
        MINIO_SECRET_KEY="secret",
        MINIO_BUCKET="bucket",
    )


def test_generates_request_and_trace_ids_and_exposes_typed_context() -> None:
    app = create_app(settings=make_settings(), container_factory=FakeContainer)

    @app.get("/context")
    async def context(
        value: Annotated[RequestContext, Depends(get_request_context)],
    ) -> dict[str, str | None]:
        return {
            "request_id": value.request_id,
            "trace_id": value.trace_id,
            "user_id": value.user_id,
            "tenant_id": value.tenant_id,
            "method": value.method,
            "path": value.path,
            "client_ip": value.client_ip,
            "started_at": value.started_at.isoformat(),
        }

    with TestClient(app) as client:
        response = client.get("/context")

    body = response.json()
    UUID(body["request_id"])
    assert len(body["trace_id"]) == 32
    assert body["user_id"] is None
    assert body["tenant_id"] is None
    assert body["method"] == "GET"
    assert body["path"] == "/context"
    assert body["client_ip"] == "testclient"
    assert datetime.fromisoformat(body["started_at"]).tzinfo is not None
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert response.headers["X-Trace-ID"] == body["trace_id"]


def test_preserves_safe_request_id_and_w3c_trace_id() -> None:
    app = create_app(settings=make_settings(), container_factory=FakeContainer)
    trace_id = "0123456789abcdef0123456789abcdef"

    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={
                "X-Request-ID": "gateway-request_123",
                "traceparent": f"00-{trace_id}-0123456789abcdef-01",
            },
        )

    assert response.headers["X-Request-ID"] == "gateway-request_123"
    assert response.headers["X-Trace-ID"] == trace_id


def test_replaces_unsafe_request_id() -> None:
    app = create_app(settings=make_settings(), container_factory=FakeContainer)

    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "unsafe value"})

    assert response.headers["X-Request-ID"] != "unsafe value"
    UUID(response.headers["X-Request-ID"])
