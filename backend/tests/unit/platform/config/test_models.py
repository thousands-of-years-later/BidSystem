"""Unit tests for cohesive, validated configuration views."""

import pytest
from pydantic import SecretStr, ValidationError

from bid_system.platform.config.models import (
    ApiSettings,
    AppSettings,
    AuthSettings,
    Environment,
    RuntimeLimitsSettings,
)


def _settings(**overrides: str) -> AppSettings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+psycopg://user:password@localhost:5432/bid_system",
        "REDIS_URL": "redis://localhost:6379/0",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "access-key",
        "MINIO_SECRET_KEY": "secret-key",
        "MINIO_BUCKET": "bid-system",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def test_builds_cohesive_settings_views() -> None:
    settings = _settings()

    assert settings.environment is Environment.TEST
    assert settings.database.url.get_secret_value().endswith("/bid_system")
    assert settings.redis.max_connections > 0
    assert settings.minio.endpoint == "localhost:9000"
    assert settings.runtime_limits.retry_max_attempts >= 1
    assert settings.auth.enabled is False
    assert settings.tracing.enabled is False


def test_enabled_auth_requires_complete_jwt_configuration() -> None:
    with pytest.raises(ValidationError, match="JWT_ALGORITHM"):
        _settings(AUTH_ENABLED="true")


def test_enabled_auth_accepts_complete_configuration() -> None:
    settings = _settings(
        AUTH_ENABLED="true",
        JWT_ALGORITHM="HS256",
        JWT_SIGNING_KEY="a-test-only-signing-key",
        JWT_ISSUER="bid-system",
        JWT_AUDIENCE="bid-system-api",
    )

    assert settings.auth == AuthSettings(
        enabled=True,
        algorithm="HS256",
        signing_key=SecretStr("a-test-only-signing-key"),
        issuer="bid-system",
        audience="bid-system-api",
        access_token_ttl_seconds=900,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("HTTP_TIMEOUT_SECONDS", "0"),
        ("RETRY_MAX_ATTEMPTS", "0"),
        ("RETRY_BASE_DELAY_SECONDS", "0"),
        ("LLM_MAX_CONCURRENCY", "0"),
        ("OCR_MAX_CONCURRENCY", "0"),
    ),
)
def test_rejects_invalid_runtime_limits(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_rejects_retry_max_delay_below_base_delay() -> None:
    with pytest.raises(ValidationError, match="RETRY_MAX_DELAY_SECONDS"):
        _settings(RETRY_BASE_DELAY_SECONDS="2", RETRY_MAX_DELAY_SECONDS="1")


@pytest.mark.parametrize(
    "origin",
    ("localhost:3000", "https://user:password@example.test", "https://example.test/path"),
)
def test_rejects_invalid_cors_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        ApiSettings(
            title="Bid System API",
            description="API",
            prefix="/api/v1",
            docs_enabled=True,
            cors_origins=(origin,),
            trusted_hosts=("localhost",),
            gzip_minimum_size_bytes=1024,
            max_request_body_bytes=1024,
            readiness_timeout_seconds=3,
            hsts_enabled=False,
        )


def test_runtime_limits_are_frozen() -> None:
    limits = _settings().runtime_limits

    with pytest.raises(ValidationError):
        RuntimeLimitsSettings(
            http_timeout_seconds=limits.http_timeout_seconds,
            retry_max_attempts=limits.retry_max_attempts,
            retry_base_delay_seconds=limits.retry_base_delay_seconds,
            retry_max_delay_seconds=0.1,
            llm_max_concurrency=limits.llm_max_concurrency,
            ocr_max_concurrency=limits.ocr_max_concurrency,
        )
