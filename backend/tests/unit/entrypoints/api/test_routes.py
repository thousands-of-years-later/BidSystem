"""Health and readiness route tests."""

from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from bid_system.entrypoints.api.app import create_app
from bid_system.platform.config import AppSettings


@dataclass
class FakeResource:
    fail: bool = False
    client: str = "fake"

    async def probe(self) -> None:
        if self.fail:
            raise RuntimeError("unavailable")

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


def test_readiness_reports_all_critical_resources() -> None:
    settings = make_settings()
    app = create_app(settings=settings, container_factory=FakeContainer)

    with TestClient(app) as client:
        response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "code": "SUCCESS",
        "message": "success",
        "data": {
            "status": "ready",
            "checks": {"database": "up", "redis": "up", "object_store": "up"},
        },
        "request_id": response.headers["X-Request-ID"],
    }


def test_readiness_returns_503_without_leaking_dependency_error() -> None:
    settings = make_settings()

    def container_factory(value: AppSettings) -> FakeContainer:
        container = FakeContainer(value)
        container.redis = FakeResource(fail=True)
        return container

    app = create_app(settings=settings, container_factory=container_factory)

    with TestClient(app) as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "code": "SERVICE_UNAVAILABLE",
        "message": "关键依赖尚未就绪",
        "details": [
            {
                "location": ["checks", "redis"],
                "message": "依赖不可用",
                "error_type": "dependency_down",
            }
        ],
        "request_id": response.headers["X-Request-ID"],
    }
    assert "unavailable" not in response.text


def test_authentication_routes_are_exposed_under_versioned_api() -> None:
    app = create_app(settings=make_settings(), container_factory=FakeContainer)

    paths = app.openapi()["paths"]

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/logout" in paths
    assert "security" not in paths["/api/v1/auth/login"]["post"]
    assert paths["/api/v1/auth/register"]["post"]["security"] == [{"HTTPBearer": []}]
    assert paths["/api/v1/version"]["get"]["security"] == [{"HTTPBearer": []}]
