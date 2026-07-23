"""Application factory contract tests."""

from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from bid_system.entrypoints.api.app import create_app
from bid_system.platform.config import AppSettings


@dataclass
class FakeResource:
    """Controllable readiness resource."""

    fail: bool = False
    client: str = "fake"

    async def probe(self) -> None:
        if self.fail:
            raise RuntimeError("unavailable")

    async def close(self) -> None:
        return None


@dataclass
class FakeContainer:
    """Test lifecycle container with no external I/O."""

    settings: AppSettings
    database: FakeResource = field(default_factory=FakeResource)
    redis: FakeResource = field(default_factory=FakeResource)
    minio: FakeResource = field(default_factory=FakeResource)
    started: bool = False
    closed: bool = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True


def make_settings(*, environment: str = "test") -> AppSettings:
    return AppSettings(
        APP_ENV=environment,
        DATABASE_URL="postgresql+psycopg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="access",
        MINIO_SECRET_KEY="secret",
        MINIO_BUCKET="bucket",
    )


def test_create_app_exposes_metadata_routes_and_unique_operation_ids() -> None:
    settings = make_settings()
    app = create_app(settings=settings, container_factory=FakeContainer)

    with TestClient(app) as client:
        health_response = client.get("/health")
        version_response = client.get("/api/v1/version")
        schema_response = client.get("/openapi.json")

    assert app.title == "Bid System API"
    assert app.version == "0.1.0"
    assert health_response.status_code == 200
    assert health_response.json() == {
        "code": "SUCCESS",
        "message": "success",
        "data": {"status": "alive"},
        "request_id": health_response.headers["X-Request-ID"],
    }
    assert health_response.headers["X-App-Version"] == "0.1.0"
    assert version_response.status_code == 401
    assert version_response.json()["code"] == "AUTHENTICATION_REQUIRED"
    operation_ids = [
        operation["operationId"]
        for path_item in schema_response.json()["paths"].values()
        for operation in path_item.values()
    ]
    assert len(operation_ids) == len(set(operation_ids))


def test_non_production_app_uses_scalar_as_its_api_reference() -> None:
    settings = make_settings()
    app = create_app(settings=settings, container_factory=FakeContainer)

    with TestClient(app) as client:
        docs_response = client.get("/docs")
        redoc_response = client.get("/redoc")

    assert docs_response.status_code == 200
    assert "Scalar" in docs_response.text
    assert "/openapi.json" in docs_response.text
    assert redoc_response.status_code == 404


def test_production_app_disables_documentation_endpoints() -> None:
    settings = make_settings(environment="prod")
    app = create_app(settings=settings, container_factory=FakeContainer)

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
