"""Immutable, validated application configuration models."""

from enum import StrEnum
from typing import Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_POOL_SIZE = 5
DEFAULT_DATABASE_MAX_OVERFLOW = 10
DEFAULT_DATABASE_POOL_TIMEOUT_SECONDS = 30.0
DEFAULT_REDIS_MAX_CONNECTIONS = 20
DEFAULT_CELERY_BROKER_URL = SecretStr("amqp://bid_system:bid_system_dev@localhost:5672//")
DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY_SECONDS = 0.5
DEFAULT_RETRY_MAX_DELAY_SECONDS = 5.0
DEFAULT_LLM_MAX_CONCURRENCY = 4
DEFAULT_OCR_MAX_CONCURRENCY = 4
DEFAULT_STARTUP_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0
DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 900
DEFAULT_REFRESH_TOKEN_ABSOLUTE_TTL_SECONDS = 30 * 24 * 60 * 60
DEFAULT_REFRESH_TOKEN_IDLE_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_ARGON2_MEMORY_COST_KIB = 19_456
DEFAULT_ARGON2_TIME_COST = 2
DEFAULT_ARGON2_PARALLELISM = 1
SUPPORTED_JWT_ALGORITHM = "RS256"
DEFAULT_GZIP_MINIMUM_SIZE_BYTES = 1024
DEFAULT_MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024
DEFAULT_DOCUMENT_UPLOAD_REQUEST_BODY_BYTES = 201 * 1024 * 1024
DEFAULT_DOCUMENT_CLAMAV_HOST = "localhost"
DEFAULT_DOCUMENT_CLAMAV_PORT = 3310
DEFAULT_DOCUMENT_CLAMAV_TIMEOUT_SECONDS = 30.0
DEFAULT_DOCUMENT_LIBREOFFICE_EXECUTABLE = "libreoffice"
DEFAULT_DOCUMENT_CONVERSION_TIMEOUT_SECONDS = 120.0
DEFAULT_READINESS_TIMEOUT_SECONDS = 3.0
DEFAULT_API_TITLE = "Bid System API"
DEFAULT_API_DESCRIPTION = "HTTP API for the bid agent platform."
DEFAULT_API_PREFIX = "/api/v1"
DEFAULT_TRUSTED_HOSTS = ("localhost", "testserver")
DEFAULT_TRACE_SERVICE_NAME = "bid-system"
DEFAULT_METRIC_EXPORT_INTERVAL_SECONDS = 60.0
DEFAULT_WORKER_QUEUE_NAME = "bid-system"
DEFAULT_WORKER_CONCURRENCY = 2
DEFAULT_WORKER_SOFT_TIME_LIMIT_SECONDS = 300
DEFAULT_WORKER_HARD_TIME_LIMIT_SECONDS = 330
DEFAULT_WORKER_MAX_RETRIES = 3
DEFAULT_WORKER_RETRY_BASE_DELAY_SECONDS = 5
DEFAULT_WORKER_RETRY_MAX_DELAY_SECONDS = 300
DEFAULT_WORKER_PREFETCH_MULTIPLIER = 1
DEFAULT_WORKER_DEAD_LETTER_QUEUE_NAME = "bid-system.dead"
DEFAULT_WORKER_DELIVERY_LIMIT = 5
SUPPORTED_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})
DEVELOPMENT_CREDENTIALS = frozenset({"bid_system_dev", "bid_system_dev_secret"})


class Environment(StrEnum):
    """Supported deployment environments."""

    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class DatabaseSettings(BaseModel):
    """PostgreSQL connection and pool settings."""

    model_config = {"frozen": True}

    url: SecretStr
    pool_size: int = Field(ge=1)
    max_overflow: int = Field(ge=0)
    pool_timeout_seconds: float = Field(gt=0)


class RedisSettings(BaseModel):
    """Redis connection and pool settings."""

    model_config = {"frozen": True}

    url: SecretStr
    max_connections: int = Field(ge=1)


class CelerySettings(BaseModel):
    """Celery broker connection settings."""

    model_config = {"frozen": True}

    broker_url: SecretStr


class MinioSettings(BaseModel):
    """MinIO endpoint, credentials, and bucket settings."""

    model_config = {"frozen": True}

    endpoint: str = Field(min_length=1)
    access_key: SecretStr
    secret_key: SecretStr
    bucket: str = Field(min_length=1)
    secure: bool


class DocumentProcessingSettings(BaseModel):
    """Security scanning, conversion, and upload-envelope settings."""

    model_config = {"frozen": True}

    clamav_host: str = Field(min_length=1)
    clamav_port: int = Field(ge=1, le=65_535)
    clamav_timeout_seconds: float = Field(gt=0)
    libreoffice_executable: str = Field(min_length=1)
    conversion_timeout_seconds: float = Field(gt=0)
    max_request_body_bytes: int = Field(gt=200 * 1024 * 1024)


class ProviderSettings(BaseModel):
    """Configuration shared by optional HTTP-based LLM and OCR providers."""

    model_config = {"frozen": True}

    enabled: bool
    base_url: str | None
    api_key: SecretStr | None
    model: str | None
    probe_on_startup: bool


class RuntimeLimitsSettings(BaseModel):
    """External-call retry, timeout, and concurrency limits."""

    model_config = {"frozen": True}

    http_timeout_seconds: float = Field(gt=0)
    retry_max_attempts: int = Field(ge=1)
    retry_base_delay_seconds: float = Field(gt=0)
    retry_max_delay_seconds: float = Field(gt=0)
    llm_max_concurrency: int = Field(ge=1)
    ocr_max_concurrency: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_retry_delay_range(self) -> Self:
        """Ensure capped backoff cannot be shorter than its initial delay."""
        if self.retry_max_delay_seconds < self.retry_base_delay_seconds:
            raise ValueError("RETRY_MAX_DELAY_SECONDS must be >= RETRY_BASE_DELAY_SECONDS")
        return self


class StartupSettings(BaseModel):
    """Resource startup and graceful-shutdown limits in seconds."""

    model_config = {"frozen": True}

    connect_timeout_seconds: float = Field(gt=0)
    shutdown_timeout_seconds: float = Field(gt=0)


class LoggingSettings(BaseModel):
    """Bootstrap logging configuration."""

    model_config = {"frozen": True}

    level: str
    json_output: bool

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        """Reject misspelled levels instead of silently changing logging behavior."""
        normalized = value.upper()
        if normalized not in SUPPORTED_LOG_LEVELS:
            raise ValueError("LOG_LEVEL is unsupported")
        return normalized


class TracingSettings(BaseModel):
    """Trace metadata and optional OTLP destination."""

    model_config = {"frozen": True}

    enabled: bool
    service_name: str = Field(min_length=1)
    otlp_endpoint: str | None


class MetricsSettings(BaseModel):
    """Metric metadata and periodic OTLP export settings."""

    model_config = {"frozen": True}

    enabled: bool
    service_name: str = Field(min_length=1)
    otlp_endpoint: str | None
    export_interval_seconds: float = Field(gt=0)


class WorkerSettings(BaseModel):
    """Validated Celery worker delivery and execution policy."""

    model_config = {"frozen": True}

    queue_name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9._-]+$")
    concurrency: int = Field(ge=1)
    soft_time_limit_seconds: int = Field(ge=1)
    hard_time_limit_seconds: int = Field(ge=1)
    max_retries: int = Field(ge=0)
    retry_base_delay_seconds: int = Field(ge=1)
    retry_max_delay_seconds: int = Field(ge=1)
    prefetch_multiplier: int = Field(ge=1)
    dead_letter_queue_name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9._-]+$")
    delivery_limit: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_delivery_windows(self) -> Self:
        """Validate task execution and retry windows."""
        if self.hard_time_limit_seconds <= self.soft_time_limit_seconds:
            raise ValueError("WORKER_HARD_TIME_LIMIT_SECONDS must exceed the soft limit")
        if self.retry_max_delay_seconds < self.retry_base_delay_seconds:
            raise ValueError("WORKER_RETRY_MAX_DELAY_SECONDS must be >= the base delay")
        if self.dead_letter_queue_name == self.queue_name:
            raise ValueError("WORKER_DEAD_LETTER_QUEUE_NAME must differ from WORKER_QUEUE_NAME")
        return self


class JwtVerificationKeySettings(BaseModel):
    """One public JWT verification key addressable by its immutable key id."""

    model_config = {"frozen": True}

    key_id: str = Field(min_length=1)
    public_key: SecretStr


class AuthSettings(BaseModel):
    """Validated authentication cryptography and session policy."""

    model_config = {"frozen": True}

    enabled: bool
    algorithm: str | None
    active_key_id: str | None
    signing_private_key: SecretStr | None
    verification_keys: tuple[JwtVerificationKeySettings, ...]
    issuer: str | None
    audience: str | None
    access_token_ttl_seconds: int = Field(ge=1)
    refresh_token_absolute_ttl_seconds: int = Field(ge=1)
    refresh_token_idle_ttl_seconds: int = Field(ge=1)
    refresh_cookie_secure: bool
    argon2_memory_cost_kib: int = Field(ge=DEFAULT_ARGON2_MEMORY_COST_KIB)
    argon2_time_cost: int = Field(ge=DEFAULT_ARGON2_TIME_COST)
    argon2_parallelism: int = Field(ge=DEFAULT_ARGON2_PARALLELISM)
    default_tenant_id: str = Field(default="default", min_length=1, max_length=64)
    initial_manager_username: str | None = None
    initial_manager_password: SecretStr | None = None


class ApiSettings(BaseModel):
    """HTTP application metadata, exposure policy, and transport limits."""

    model_config = {"frozen": True}

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    prefix: str = Field(pattern=r"^/(?:[^/]+(?:/[^/]+)*)?$")
    docs_enabled: bool
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...] = Field(min_length=1)
    gzip_minimum_size_bytes: int = Field(ge=1)
    max_request_body_bytes: int = Field(ge=1)
    readiness_timeout_seconds: float = Field(gt=0)
    hsts_enabled: bool

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Accept only credential-free HTTP origins without paths."""
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("API_CORS_ORIGINS entries must be HTTP origins")
        return values

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject URL-shaped trusted hosts and blank entries."""
        if any(not value.strip() or "://" in value or "/" in value for value in values):
            raise ValueError("API_TRUSTED_HOSTS entries must be host patterns")
        return values


class AppSettings(BaseSettings):
    """Root settings model; environment variables override the dotenv source."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Field(default=Environment.DEV, validation_alias="APP_ENV")
    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    database_pool_size: int = Field(
        default=DEFAULT_DATABASE_POOL_SIZE,
        ge=1,
        validation_alias="DATABASE_POOL_SIZE",
    )
    database_max_overflow: int = Field(
        default=DEFAULT_DATABASE_MAX_OVERFLOW,
        ge=0,
        validation_alias="DATABASE_MAX_OVERFLOW",
    )
    database_pool_timeout_seconds: float = Field(
        default=DEFAULT_DATABASE_POOL_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="DATABASE_POOL_TIMEOUT_SECONDS",
    )
    redis_url: SecretStr = Field(validation_alias="REDIS_URL")
    redis_max_connections: int = Field(
        default=DEFAULT_REDIS_MAX_CONNECTIONS,
        ge=1,
        validation_alias="REDIS_MAX_CONNECTIONS",
    )
    celery_broker_url: SecretStr = Field(
        default=DEFAULT_CELERY_BROKER_URL,
        validation_alias="CELERY_BROKER_URL",
    )
    minio_endpoint: str = Field(min_length=1, validation_alias="MINIO_ENDPOINT")
    minio_access_key: SecretStr = Field(
        validation_alias=AliasChoices("MINIO_ACCESS_KEY", "MINIO_ROOT_USER")
    )
    minio_secret_key: SecretStr = Field(
        validation_alias=AliasChoices("MINIO_SECRET_KEY", "MINIO_ROOT_PASSWORD")
    )
    minio_bucket: str = Field(min_length=1, validation_alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, validation_alias="MINIO_SECURE")
    document_clamav_host: str = Field(
        default=DEFAULT_DOCUMENT_CLAMAV_HOST,
        min_length=1,
        validation_alias="DOCUMENT_CLAMAV_HOST",
    )
    document_clamav_port: int = Field(
        default=DEFAULT_DOCUMENT_CLAMAV_PORT,
        ge=1,
        le=65_535,
        validation_alias="DOCUMENT_CLAMAV_PORT",
    )
    document_clamav_timeout_seconds: float = Field(
        default=DEFAULT_DOCUMENT_CLAMAV_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="DOCUMENT_CLAMAV_TIMEOUT_SECONDS",
    )
    document_libreoffice_executable: str = Field(
        default=DEFAULT_DOCUMENT_LIBREOFFICE_EXECUTABLE,
        min_length=1,
        validation_alias="DOCUMENT_LIBREOFFICE_EXECUTABLE",
    )
    document_conversion_timeout_seconds: float = Field(
        default=DEFAULT_DOCUMENT_CONVERSION_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="DOCUMENT_CONVERSION_TIMEOUT_SECONDS",
    )
    document_upload_request_body_bytes: int = Field(
        default=DEFAULT_DOCUMENT_UPLOAD_REQUEST_BODY_BYTES,
        gt=200 * 1024 * 1024,
        validation_alias="DOCUMENT_UPLOAD_REQUEST_BODY_BYTES",
    )
    llm_enabled: bool = Field(default=False, validation_alias="LLM_ENABLED")
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    llm_api_key: SecretStr | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_model: str | None = Field(default=None, validation_alias="LLM_MODEL")
    llm_probe_on_startup: bool = Field(default=False, validation_alias="LLM_PROBE_ON_STARTUP")
    ocr_enabled: bool = Field(default=False, validation_alias="OCR_ENABLED")
    ocr_base_url: str | None = Field(default=None, validation_alias="OCR_BASE_URL")
    ocr_api_key: SecretStr | None = Field(default=None, validation_alias="OCR_API_KEY")
    ocr_model: str | None = Field(default=None, validation_alias="OCR_MODEL")
    ocr_probe_on_startup: bool = Field(default=False, validation_alias="OCR_PROBE_ON_STARTUP")
    http_timeout_seconds: float = Field(
        default=DEFAULT_HTTP_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="HTTP_TIMEOUT_SECONDS",
    )
    retry_max_attempts: int = Field(
        default=DEFAULT_RETRY_MAX_ATTEMPTS,
        ge=1,
        validation_alias="RETRY_MAX_ATTEMPTS",
    )
    retry_base_delay_seconds: float = Field(
        default=DEFAULT_RETRY_BASE_DELAY_SECONDS,
        gt=0,
        validation_alias="RETRY_BASE_DELAY_SECONDS",
    )
    retry_max_delay_seconds: float = Field(
        default=DEFAULT_RETRY_MAX_DELAY_SECONDS,
        gt=0,
        validation_alias="RETRY_MAX_DELAY_SECONDS",
    )
    llm_max_concurrency: int = Field(
        default=DEFAULT_LLM_MAX_CONCURRENCY,
        ge=1,
        validation_alias="LLM_MAX_CONCURRENCY",
    )
    ocr_max_concurrency: int = Field(
        default=DEFAULT_OCR_MAX_CONCURRENCY,
        ge=1,
        validation_alias="OCR_MAX_CONCURRENCY",
    )
    startup_connect_timeout_seconds: float = Field(
        default=DEFAULT_STARTUP_CONNECT_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="STARTUP_CONNECT_TIMEOUT_SECONDS",
    )
    shutdown_timeout_seconds: float = Field(
        default=DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="SHUTDOWN_TIMEOUT_SECONDS",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_json: bool = Field(default=False, validation_alias="LOG_JSON")
    tracing_enabled: bool = Field(default=False, validation_alias="TRACING_ENABLED")
    tracing_service_name: str = Field(
        default=DEFAULT_TRACE_SERVICE_NAME,
        min_length=1,
        validation_alias="TRACING_SERVICE_NAME",
    )
    tracing_otlp_endpoint: str | None = Field(
        default=None,
        validation_alias="TRACING_OTLP_ENDPOINT",
    )
    metrics_enabled: bool = Field(default=False, validation_alias="METRICS_ENABLED")
    metrics_export_interval_seconds: float = Field(
        default=DEFAULT_METRIC_EXPORT_INTERVAL_SECONDS,
        gt=0,
        validation_alias="METRICS_EXPORT_INTERVAL_SECONDS",
    )
    worker_queue_name: str = Field(
        default=DEFAULT_WORKER_QUEUE_NAME,
        validation_alias="WORKER_QUEUE_NAME",
    )
    worker_concurrency: int = Field(
        default=DEFAULT_WORKER_CONCURRENCY,
        ge=1,
        validation_alias="WORKER_CONCURRENCY",
    )
    worker_soft_time_limit_seconds: int = Field(
        default=DEFAULT_WORKER_SOFT_TIME_LIMIT_SECONDS,
        ge=1,
        validation_alias="WORKER_SOFT_TIME_LIMIT_SECONDS",
    )
    worker_hard_time_limit_seconds: int = Field(
        default=DEFAULT_WORKER_HARD_TIME_LIMIT_SECONDS,
        ge=1,
        validation_alias="WORKER_HARD_TIME_LIMIT_SECONDS",
    )
    worker_max_retries: int = Field(
        default=DEFAULT_WORKER_MAX_RETRIES,
        ge=0,
        validation_alias="WORKER_MAX_RETRIES",
    )
    worker_retry_base_delay_seconds: int = Field(
        default=DEFAULT_WORKER_RETRY_BASE_DELAY_SECONDS,
        ge=1,
        validation_alias="WORKER_RETRY_BASE_DELAY_SECONDS",
    )
    worker_retry_max_delay_seconds: int = Field(
        default=DEFAULT_WORKER_RETRY_MAX_DELAY_SECONDS,
        ge=1,
        validation_alias="WORKER_RETRY_MAX_DELAY_SECONDS",
    )
    worker_prefetch_multiplier: int = Field(
        default=DEFAULT_WORKER_PREFETCH_MULTIPLIER,
        ge=1,
        validation_alias="WORKER_PREFETCH_MULTIPLIER",
    )
    worker_dead_letter_queue_name: str = Field(
        default=DEFAULT_WORKER_DEAD_LETTER_QUEUE_NAME,
        validation_alias="WORKER_DEAD_LETTER_QUEUE_NAME",
    )
    worker_delivery_limit: int = Field(
        default=DEFAULT_WORKER_DELIVERY_LIMIT,
        ge=1,
        validation_alias="WORKER_DELIVERY_LIMIT",
    )
    auth_enabled: bool = Field(default=False, validation_alias="AUTH_ENABLED")
    jwt_algorithm: str | None = Field(default=None, validation_alias="JWT_ALGORITHM")
    jwt_active_key_id: str | None = Field(default=None, validation_alias="JWT_ACTIVE_KEY_ID")
    jwt_signing_private_key: SecretStr | None = Field(
        default=None,
        validation_alias="JWT_SIGNING_PRIVATE_KEY",
    )
    jwt_verification_keys: tuple[JwtVerificationKeySettings, ...] = Field(
        default=(),
        validation_alias="JWT_VERIFICATION_KEYS",
    )
    jwt_issuer: str | None = Field(default=None, validation_alias="JWT_ISSUER")
    jwt_audience: str | None = Field(default=None, validation_alias="JWT_AUDIENCE")
    jwt_access_token_ttl_seconds: int = Field(
        default=DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        ge=1,
        validation_alias="JWT_ACCESS_TOKEN_TTL_SECONDS",
    )
    refresh_token_absolute_ttl_seconds: int = Field(
        default=DEFAULT_REFRESH_TOKEN_ABSOLUTE_TTL_SECONDS,
        ge=1,
        validation_alias="REFRESH_TOKEN_ABSOLUTE_TTL_SECONDS",
    )
    refresh_token_idle_ttl_seconds: int = Field(
        default=DEFAULT_REFRESH_TOKEN_IDLE_TTL_SECONDS,
        ge=1,
        validation_alias="REFRESH_TOKEN_IDLE_TTL_SECONDS",
    )
    refresh_cookie_secure: bool = Field(default=True, validation_alias="REFRESH_COOKIE_SECURE")
    argon2_memory_cost_kib: int = Field(
        default=DEFAULT_ARGON2_MEMORY_COST_KIB,
        ge=DEFAULT_ARGON2_MEMORY_COST_KIB,
        validation_alias="ARGON2_MEMORY_COST_KIB",
    )
    argon2_time_cost: int = Field(
        default=DEFAULT_ARGON2_TIME_COST,
        ge=DEFAULT_ARGON2_TIME_COST,
        validation_alias="ARGON2_TIME_COST",
    )
    argon2_parallelism: int = Field(
        default=DEFAULT_ARGON2_PARALLELISM,
        ge=DEFAULT_ARGON2_PARALLELISM,
        validation_alias="ARGON2_PARALLELISM",
    )
    auth_default_tenant_id: str = Field(
        default="default",
        min_length=1,
        max_length=64,
        validation_alias="AUTH_DEFAULT_TENANT_ID",
    )
    initial_manager_username: str | None = Field(
        default=None,
        validation_alias="INITIAL_MANAGER_USERNAME",
    )
    initial_manager_password: SecretStr | None = Field(
        default=None,
        validation_alias="INITIAL_MANAGER_PASSWORD",
    )
    api_title: str = Field(default=DEFAULT_API_TITLE, validation_alias="API_TITLE")
    api_description: str = Field(
        default=DEFAULT_API_DESCRIPTION,
        validation_alias="API_DESCRIPTION",
    )
    api_prefix: str = Field(default=DEFAULT_API_PREFIX, validation_alias="API_PREFIX")
    api_cors_origins: tuple[str, ...] = Field(default=(), validation_alias="API_CORS_ORIGINS")
    api_trusted_hosts: tuple[str, ...] = Field(
        default=DEFAULT_TRUSTED_HOSTS,
        validation_alias="API_TRUSTED_HOSTS",
    )
    api_gzip_minimum_size_bytes: int = Field(
        default=DEFAULT_GZIP_MINIMUM_SIZE_BYTES,
        ge=1,
        validation_alias="API_GZIP_MINIMUM_SIZE_BYTES",
    )
    api_max_request_body_bytes: int = Field(
        default=DEFAULT_MAX_REQUEST_BODY_BYTES,
        ge=1,
        validation_alias="API_MAX_REQUEST_BODY_BYTES",
    )
    api_readiness_timeout_seconds: float = Field(
        default=DEFAULT_READINESS_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="API_READINESS_TIMEOUT_SECONDS",
    )
    api_hsts_enabled: bool = Field(default=False, validation_alias="API_HSTS_ENABLED")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Restrict the engine URL to the selected async psycopg driver."""
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: SecretStr) -> SecretStr:
        """Restrict Redis URLs to supported clear-text or TLS schemes."""
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must use redis:// or rediss://")
        return value

    @field_validator("celery_broker_url")
    @classmethod
    def validate_celery_broker_url(cls, value: SecretStr) -> SecretStr:
        """Require RabbitMQ's AMQP transport for Celery delivery."""
        parsed = urlsplit(value.get_secret_value())
        if (
            parsed.scheme not in {"amqp", "amqps"}
            or not parsed.hostname
            or not parsed.username
            or not parsed.password
        ):
            raise ValueError(
                "CELERY_BROKER_URL must use amqp:// or amqps:// and include broker credentials"
            )
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Validate the root log level at process startup."""
        return LoggingSettings(level=value, json_output=False).level

    @model_validator(mode="after")
    def validate_cross_field_configuration(self) -> Self:
        """Reject incomplete providers, auth, unsafe production values, and bad ranges."""
        self._validate_provider(
            "LLM", self.llm_enabled, self.llm_base_url, self.llm_api_key, self.llm_model
        )
        self._validate_provider(
            "OCR", self.ocr_enabled, self.ocr_base_url, self.ocr_api_key, self.ocr_model
        )
        if self.refresh_token_idle_ttl_seconds > self.refresh_token_absolute_ttl_seconds:
            raise ValueError(
                "REFRESH_TOKEN_IDLE_TTL_SECONDS must be <= REFRESH_TOKEN_ABSOLUTE_TTL_SECONDS"
            )
        if self.auth_enabled and not all(
            (
                self.jwt_algorithm,
                self.jwt_active_key_id,
                self._secret_value(self.jwt_signing_private_key),
                self.jwt_verification_keys,
                self.jwt_issuer,
                self.jwt_audience,
            )
        ):
            raise ValueError(
                "JWT_ALGORITHM, JWT_ACTIVE_KEY_ID, JWT_SIGNING_PRIVATE_KEY, "
                "JWT_VERIFICATION_KEYS, JWT_ISSUER and JWT_AUDIENCE are required when "
                "AUTH_ENABLED=true"
            )
        if self.auth_enabled and self.jwt_algorithm != SUPPORTED_JWT_ALGORITHM:
            raise ValueError(f"JWT_ALGORITHM must be {SUPPORTED_JWT_ALGORITHM}")
        verification_key_ids = {key.key_id for key in self.jwt_verification_keys}
        if len(verification_key_ids) != len(self.jwt_verification_keys):
            raise ValueError("JWT_VERIFICATION_KEYS key ids must be unique")
        if self.auth_enabled and self.jwt_active_key_id not in verification_key_ids:
            raise ValueError("JWT_ACTIVE_KEY_ID must exist in JWT_VERIFICATION_KEYS")
        if self.auth_enabled and not (
            self.initial_manager_username and self._secret_value(self.initial_manager_password)
        ):
            raise ValueError(
                "INITIAL_MANAGER_USERNAME and INITIAL_MANAGER_PASSWORD are required when "
                "AUTH_ENABLED=true"
            )
        RuntimeLimitsSettings(
            http_timeout_seconds=self.http_timeout_seconds,
            retry_max_attempts=self.retry_max_attempts,
            retry_base_delay_seconds=self.retry_base_delay_seconds,
            retry_max_delay_seconds=self.retry_max_delay_seconds,
            llm_max_concurrency=self.llm_max_concurrency,
            ocr_max_concurrency=self.ocr_max_concurrency,
        )
        _ = self.worker
        if (self.tracing_enabled or self.metrics_enabled) and not self.tracing_otlp_endpoint:
            raise ValueError(
                "TRACING_OTLP_ENDPOINT is required when tracing or metrics export is enabled"
            )
        if self.tracing_otlp_endpoint and urlsplit(self.tracing_otlp_endpoint).scheme not in {
            "http",
            "https",
        }:
            raise ValueError("TRACING_OTLP_ENDPOINT must use http:// or https://")
        _ = self.api
        if self.environment is Environment.PROD:
            if not self.refresh_cookie_secure:
                raise ValueError("REFRESH_COOKIE_SECURE must be true in production")
            minio_secrets = {
                self.minio_access_key.get_secret_value(),
                self.minio_secret_key.get_secret_value(),
            }
            if minio_secrets & DEVELOPMENT_CREDENTIALS:
                raise ValueError("Development MinIO credentials are forbidden in production")
        return self

    @staticmethod
    def _secret_value(value: SecretStr | None) -> str | None:
        return None if value is None else value.get_secret_value()

    @classmethod
    def _validate_provider(
        cls,
        name: str,
        enabled: bool,
        base_url: str | None,
        api_key: SecretStr | None,
        model: str | None,
    ) -> None:
        if enabled and not (base_url and cls._secret_value(api_key) and model):
            raise ValueError(
                f"{name}_BASE_URL, {name}_API_KEY and {name}_MODEL are required when enabled"
            )
        if enabled and base_url is not None and urlsplit(base_url).scheme not in {"http", "https"}:
            raise ValueError(f"{name}_BASE_URL must use http:// or https://")

    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings(
            url=self.database_url,
            pool_size=self.database_pool_size,
            max_overflow=self.database_max_overflow,
            pool_timeout_seconds=self.database_pool_timeout_seconds,
        )

    @property
    def redis(self) -> RedisSettings:
        return RedisSettings(url=self.redis_url, max_connections=self.redis_max_connections)

    @property
    def celery(self) -> CelerySettings:
        return CelerySettings(broker_url=self.celery_broker_url)

    @property
    def minio(self) -> MinioSettings:
        return MinioSettings(
            endpoint=self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            bucket=self.minio_bucket,
            secure=self.minio_secure,
        )

    @property
    def documents(self) -> DocumentProcessingSettings:
        return DocumentProcessingSettings(
            clamav_host=self.document_clamav_host,
            clamav_port=self.document_clamav_port,
            clamav_timeout_seconds=self.document_clamav_timeout_seconds,
            libreoffice_executable=self.document_libreoffice_executable,
            conversion_timeout_seconds=self.document_conversion_timeout_seconds,
            max_request_body_bytes=self.document_upload_request_body_bytes,
        )

    @property
    def llm(self) -> ProviderSettings:
        return ProviderSettings(
            enabled=self.llm_enabled,
            base_url=self.llm_base_url,
            api_key=self.llm_api_key,
            model=self.llm_model,
            probe_on_startup=self.llm_probe_on_startup,
        )

    @property
    def ocr(self) -> ProviderSettings:
        return ProviderSettings(
            enabled=self.ocr_enabled,
            base_url=self.ocr_base_url,
            api_key=self.ocr_api_key,
            model=self.ocr_model,
            probe_on_startup=self.ocr_probe_on_startup,
        )

    @property
    def runtime_limits(self) -> RuntimeLimitsSettings:
        return RuntimeLimitsSettings(
            http_timeout_seconds=self.http_timeout_seconds,
            retry_max_attempts=self.retry_max_attempts,
            retry_base_delay_seconds=self.retry_base_delay_seconds,
            retry_max_delay_seconds=self.retry_max_delay_seconds,
            llm_max_concurrency=self.llm_max_concurrency,
            ocr_max_concurrency=self.ocr_max_concurrency,
        )

    @property
    def startup(self) -> StartupSettings:
        return StartupSettings(
            connect_timeout_seconds=self.startup_connect_timeout_seconds,
            shutdown_timeout_seconds=self.shutdown_timeout_seconds,
        )

    @property
    def logging(self) -> LoggingSettings:
        return LoggingSettings(level=self.log_level, json_output=self.log_json)

    @property
    def tracing(self) -> TracingSettings:
        return TracingSettings(
            enabled=self.tracing_enabled,
            service_name=self.tracing_service_name,
            otlp_endpoint=self.tracing_otlp_endpoint,
        )

    @property
    def metrics(self) -> MetricsSettings:
        return MetricsSettings(
            enabled=self.metrics_enabled,
            service_name=self.tracing_service_name,
            otlp_endpoint=self.tracing_otlp_endpoint,
            export_interval_seconds=self.metrics_export_interval_seconds,
        )

    @property
    def worker(self) -> WorkerSettings:
        return WorkerSettings(
            queue_name=self.worker_queue_name,
            concurrency=self.worker_concurrency,
            soft_time_limit_seconds=self.worker_soft_time_limit_seconds,
            hard_time_limit_seconds=self.worker_hard_time_limit_seconds,
            max_retries=self.worker_max_retries,
            retry_base_delay_seconds=self.worker_retry_base_delay_seconds,
            retry_max_delay_seconds=self.worker_retry_max_delay_seconds,
            prefetch_multiplier=self.worker_prefetch_multiplier,
            dead_letter_queue_name=self.worker_dead_letter_queue_name,
            delivery_limit=self.worker_delivery_limit,
        )

    @property
    def auth(self) -> AuthSettings:
        return AuthSettings(
            enabled=self.auth_enabled,
            algorithm=self.jwt_algorithm,
            active_key_id=self.jwt_active_key_id,
            signing_private_key=self.jwt_signing_private_key,
            verification_keys=self.jwt_verification_keys,
            issuer=self.jwt_issuer,
            audience=self.jwt_audience,
            access_token_ttl_seconds=self.jwt_access_token_ttl_seconds,
            refresh_token_absolute_ttl_seconds=self.refresh_token_absolute_ttl_seconds,
            refresh_token_idle_ttl_seconds=self.refresh_token_idle_ttl_seconds,
            refresh_cookie_secure=self.refresh_cookie_secure,
            argon2_memory_cost_kib=self.argon2_memory_cost_kib,
            argon2_time_cost=self.argon2_time_cost,
            argon2_parallelism=self.argon2_parallelism,
            default_tenant_id=self.auth_default_tenant_id,
            initial_manager_username=self.initial_manager_username,
            initial_manager_password=self.initial_manager_password,
        )

    @property
    def api(self) -> ApiSettings:
        return ApiSettings(
            title=self.api_title,
            description=self.api_description,
            prefix=self.api_prefix,
            docs_enabled=self.environment is not Environment.PROD,
            cors_origins=self.api_cors_origins,
            trusted_hosts=self.api_trusted_hosts,
            gzip_minimum_size_bytes=self.api_gzip_minimum_size_bytes,
            max_request_body_bytes=self.api_max_request_body_bytes,
            readiness_timeout_seconds=self.api_readiness_timeout_seconds,
            hsts_enabled=self.api_hsts_enabled,
        )
