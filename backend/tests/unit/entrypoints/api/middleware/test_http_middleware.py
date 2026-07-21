"""Observable transport middleware tests."""

import logging
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from bid_system.entrypoints.api.app import create_app
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
    return _settings()


def _settings(
    *,
    cors_origins: tuple[str, ...] = (),
    trusted_hosts: tuple[str, ...] = ("localhost", "testserver"),
    gzip_minimum_size_bytes: int = 1024,
    max_request_body_bytes: int = 10 * 1024 * 1024,
) -> AppSettings:
    return AppSettings(
        APP_ENV="test",
        DATABASE_URL="postgresql+psycopg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="access",
        MINIO_SECRET_KEY="secret",
        MINIO_BUCKET="bucket",
        API_CORS_ORIGINS=cors_origins,
        API_TRUSTED_HOSTS=trusted_hosts,
        API_GZIP_MINIMUM_SIZE_BYTES=gzip_minimum_size_bytes,
        API_MAX_REQUEST_BODY_BYTES=max_request_body_bytes,
    )


def test_response_has_timing_version_and_security_headers() -> None:
    app = create_app(settings=make_settings(), container_factory=FakeContainer)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers["Server-Timing"].startswith("app;dur=")
    assert response.headers["X-App-Version"] == "0.1.0"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


@dataclass(frozen=True)
class CapturedRequestLog:
    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float


class CapturingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[CapturedRequestLog] = []

    def emit(self, record: logging.LogRecord) -> None:
        request_id = record.__dict__.get("request_id")
        method = record.__dict__.get("method")
        path = record.__dict__.get("path")
        status_code = record.__dict__.get("status_code")
        duration_ms = record.__dict__.get("duration_ms")
        if (
            isinstance(request_id, str)
            and isinstance(method, str)
            and isinstance(path, str)
            and isinstance(status_code, int)
            and isinstance(duration_ms, (int, float))
        ):
            self.records.append(
                CapturedRequestLog(
                    request_id=request_id,
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=float(duration_ms),
                )
            )


def test_access_log_contains_request_context() -> None:
    app = create_app(settings=make_settings(), container_factory=FakeContainer)
    logger = logging.getLogger("bid_system.access")
    handler = CapturingHandler()

    with TestClient(app) as client:
        logger.addHandler(handler)
        try:
            response = client.get("/health")
        finally:
            logger.removeHandler(handler)

    records = handler.records
    assert response.status_code == 200
    assert len(records) == 1
    record = records[0]
    assert record.request_id == response.headers["X-Request-ID"]
    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0


def test_cors_trusted_host_gzip_and_middleware_order() -> None:
    settings = _settings(
        cors_origins=("https://ui.example",),
        trusted_hosts=("testserver",),
        gzip_minimum_size_bytes=10,
    )
    app = create_app(settings=settings, container_factory=FakeContainer)

    @app.get("/large")
    async def large_response() -> dict[str, str]:
        return {"value": "x" * 100}

    with TestClient(app) as client:
        cors_response = client.options(
            "/health",
            headers={
                "Origin": "https://ui.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        gzip_response = client.get("/large", headers={"Accept-Encoding": "gzip"})
        rejected_response = client.get("/health", headers={"Host": "attacker.example"})

    assert cors_response.headers["Access-Control-Allow-Origin"] == "https://ui.example"
    assert gzip_response.headers["Content-Encoding"] == "gzip"
    assert rejected_response.status_code == 400
    # Outer middleware must still trace, time, and harden an inner TrustedHost rejection.
    assert rejected_response.headers["X-Request-ID"]
    assert rejected_response.headers["Server-Timing"]
    assert rejected_response.headers["X-Content-Type-Options"] == "nosniff"


def test_rejects_request_body_over_configured_limit() -> None:
    settings = _settings(max_request_body_bytes=5)
    app: FastAPI = create_app(settings=settings, container_factory=FakeContainer)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, str]:
        return {"body": (await request.body()).decode("utf-8")}

    with TestClient(app) as client:
        response = client.post("/echo", content=b"123456")

    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_BODY_TOO_LARGE"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
