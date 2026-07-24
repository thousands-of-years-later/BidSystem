"""Unit tests for cohesive, validated configuration views."""

import pytest
from pydantic import SecretStr, ValidationError

from bid_system.platform.config.models import (
    ApiSettings,
    AppSettings,
    AuthSettings,
    Environment,
    JwtVerificationKeySettings,
    RuntimeLimitsSettings,
)

TEST_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\ntest-private-key\n-----END PRIVATE KEY-----"
TEST_PUBLIC_KEY = "-----BEGIN PUBLIC KEY-----\ntest-public-key\n-----END PUBLIC KEY-----"
type SettingOverride = str | tuple[JwtVerificationKeySettings, ...]


def _verification_keys() -> tuple[JwtVerificationKeySettings, ...]:
    return (
        JwtVerificationKeySettings(
            key_id="test-key-1",
            public_key=SecretStr(TEST_PUBLIC_KEY),
        ),
    )


def _settings(**overrides: SettingOverride) -> AppSettings:
    values: dict[str, SettingOverride] = {
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
    assert settings.celery.broker_url.get_secret_value().startswith("amqp://")
    assert settings.minio.endpoint == "localhost:9000"
    assert settings.documents.clamav_host == "localhost"
    assert settings.documents.clamav_port == 3310
    assert settings.documents.max_request_body_bytes > 200 * 1024 * 1024
    assert settings.runtime_limits.retry_max_attempts >= 1
    assert settings.auth.enabled is False
    assert settings.tracing.enabled is False


def test_enabled_auth_requires_complete_jwt_configuration() -> None:
    with pytest.raises(ValidationError, match="JWT_ALGORITHM"):
        _settings(AUTH_ENABLED="true")


def test_enabled_auth_accepts_complete_configuration() -> None:
    settings = _settings(
        AUTH_ENABLED="true",
        JWT_ALGORITHM="RS256",
        JWT_ACTIVE_KEY_ID="test-key-1",
        JWT_SIGNING_PRIVATE_KEY=TEST_PRIVATE_KEY,
        JWT_VERIFICATION_KEYS=_verification_keys(),
        JWT_ISSUER="bid-system",
        JWT_AUDIENCE="bid-system-api",
        INITIAL_MANAGER_USERNAME="manager",
        INITIAL_MANAGER_PASSWORD="secure123",
    )

    assert settings.auth == AuthSettings(
        enabled=True,
        algorithm="RS256",
        active_key_id="test-key-1",
        signing_private_key=SecretStr(TEST_PRIVATE_KEY),
        verification_keys=(
            JwtVerificationKeySettings(
                key_id="test-key-1",
                public_key=SecretStr(TEST_PUBLIC_KEY),
            ),
        ),
        issuer="bid-system",
        audience="bid-system-api",
        access_token_ttl_seconds=900,
        refresh_token_absolute_ttl_seconds=2_592_000,
        refresh_token_idle_ttl_seconds=604_800,
        refresh_cookie_secure=True,
        argon2_memory_cost_kib=19_456,
        argon2_time_cost=2,
        argon2_parallelism=1,
        default_tenant_id="default",
        initial_manager_username="manager",
        initial_manager_password=SecretStr("secure123"),
    )


def test_enabled_auth_requires_initial_manager_credentials() -> None:
    with pytest.raises(ValidationError, match="INITIAL_MANAGER_USERNAME"):
        _settings(
            AUTH_ENABLED="true",
            JWT_ALGORITHM="RS256",
            JWT_ACTIVE_KEY_ID="test-key-1",
            JWT_SIGNING_PRIVATE_KEY=TEST_PRIVATE_KEY,
            JWT_VERIFICATION_KEYS=_verification_keys(),
            JWT_ISSUER="bid-system",
            JWT_AUDIENCE="bid-system-api",
        )


def test_enabled_auth_rejects_symmetric_jwt_algorithm() -> None:
    with pytest.raises(ValidationError, match="RS256"):
        _settings(
            AUTH_ENABLED="true",
            JWT_ALGORITHM="HS256",
            JWT_ACTIVE_KEY_ID="test-key-1",
            JWT_SIGNING_PRIVATE_KEY=TEST_PRIVATE_KEY,
            JWT_VERIFICATION_KEYS=_verification_keys(),
            JWT_ISSUER="bid-system",
            JWT_AUDIENCE="bid-system-api",
        )


def test_enabled_auth_requires_active_key_in_verification_key_ring() -> None:
    with pytest.raises(ValidationError, match="JWT_ACTIVE_KEY_ID"):
        _settings(
            AUTH_ENABLED="true",
            JWT_ALGORITHM="RS256",
            JWT_ACTIVE_KEY_ID="missing-key",
            JWT_SIGNING_PRIVATE_KEY=TEST_PRIVATE_KEY,
            JWT_VERIFICATION_KEYS=_verification_keys(),
            JWT_ISSUER="bid-system",
            JWT_AUDIENCE="bid-system-api",
        )


def test_rejects_refresh_idle_ttl_longer_than_absolute_ttl() -> None:
    with pytest.raises(ValidationError, match="REFRESH_TOKEN_IDLE_TTL_SECONDS"):
        _settings(
            REFRESH_TOKEN_ABSOLUTE_TTL_SECONDS="3600",
            REFRESH_TOKEN_IDLE_TTL_SECONDS="7200",
        )


def test_production_rejects_insecure_refresh_cookie() -> None:
    with pytest.raises(ValidationError, match="REFRESH_COOKIE_SECURE"):
        _settings(APP_ENV="prod", REFRESH_COOKIE_SECURE="false")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("HTTP_TIMEOUT_SECONDS", "0"),
        ("RETRY_MAX_ATTEMPTS", "0"),
        ("RETRY_BASE_DELAY_SECONDS", "0"),
        ("LLM_MAX_CONCURRENCY", "0"),
        ("OCR_MAX_CONCURRENCY", "0"),
        ("DOCUMENT_CLAMAV_PORT", "0"),
        ("DOCUMENT_CONVERSION_TIMEOUT_SECONDS", "0"),
    ),
)
def test_rejects_invalid_runtime_limits(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_rejects_retry_max_delay_below_base_delay() -> None:
    with pytest.raises(ValidationError, match="RETRY_MAX_DELAY_SECONDS"):
        _settings(RETRY_BASE_DELAY_SECONDS="2", RETRY_MAX_DELAY_SECONDS="1")


@pytest.mark.parametrize(
    "broker_url",
    (
        "redis://localhost:6379/0",
        "amqp://",
        "amqp://rabbitmq:5672//",
    ),
)
def test_rejects_invalid_celery_broker(broker_url: str) -> None:
    with pytest.raises(ValidationError, match="CELERY_BROKER_URL"):
        _settings(CELERY_BROKER_URL=broker_url)


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
