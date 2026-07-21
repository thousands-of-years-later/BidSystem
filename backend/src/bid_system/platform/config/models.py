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
DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY_SECONDS = 0.5
DEFAULT_RETRY_MAX_DELAY_SECONDS = 5.0
DEFAULT_LLM_MAX_CONCURRENCY = 4
DEFAULT_OCR_MAX_CONCURRENCY = 4
DEFAULT_STARTUP_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0
DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 900
DEFAULT_GZIP_MINIMUM_SIZE_BYTES = 1024
DEFAULT_MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024
DEFAULT_READINESS_TIMEOUT_SECONDS = 3.0
DEFAULT_API_TITLE = "Bid System API"
DEFAULT_API_DESCRIPTION = "HTTP API for the bid agent platform."
DEFAULT_API_PREFIX = "/api/v1"
DEFAULT_TRUSTED_HOSTS = ("localhost", "testserver")
DEFAULT_TRACE_SERVICE_NAME = "bid-system"
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


class MinioSettings(BaseModel):
    """MinIO endpoint, credentials, and bucket settings."""

    model_config = {"frozen": True}

    endpoint: str = Field(min_length=1)
    access_key: SecretStr
    secret_key: SecretStr
    bucket: str = Field(min_length=1)
    secure: bool


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


class AuthSettings(BaseModel):
    """JWT verification/signing configuration exposed to a future auth adapter."""

    model_config = {"frozen": True}

    enabled: bool
    algorithm: str | None
    signing_key: SecretStr | None
    issuer: str | None
    audience: str | None
    access_token_ttl_seconds: int = Field(ge=1)


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
    minio_endpoint: str = Field(min_length=1, validation_alias="MINIO_ENDPOINT")
    minio_access_key: SecretStr = Field(
        validation_alias=AliasChoices("MINIO_ACCESS_KEY", "MINIO_ROOT_USER")
    )
    minio_secret_key: SecretStr = Field(
        validation_alias=AliasChoices("MINIO_SECRET_KEY", "MINIO_ROOT_PASSWORD")
    )
    minio_bucket: str = Field(min_length=1, validation_alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, validation_alias="MINIO_SECURE")
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
    auth_enabled: bool = Field(default=False, validation_alias="AUTH_ENABLED")
    jwt_algorithm: str | None = Field(default=None, validation_alias="JWT_ALGORITHM")
    jwt_signing_key: SecretStr | None = Field(default=None, validation_alias="JWT_SIGNING_KEY")
    jwt_issuer: str | None = Field(default=None, validation_alias="JWT_ISSUER")
    jwt_audience: str | None = Field(default=None, validation_alias="JWT_AUDIENCE")
    jwt_access_token_ttl_seconds: int = Field(
        default=DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        ge=1,
        validation_alias="JWT_ACCESS_TOKEN_TTL_SECONDS",
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
        if self.auth_enabled and not all(
            (
                self.jwt_algorithm,
                self._secret_value(self.jwt_signing_key),
                self.jwt_issuer,
                self.jwt_audience,
            )
        ):
            raise ValueError(
                "JWT_ALGORITHM, JWT_SIGNING_KEY, JWT_ISSUER and JWT_AUDIENCE are required "
                "when AUTH_ENABLED=true"
            )
        RuntimeLimitsSettings(
            http_timeout_seconds=self.http_timeout_seconds,
            retry_max_attempts=self.retry_max_attempts,
            retry_base_delay_seconds=self.retry_base_delay_seconds,
            retry_max_delay_seconds=self.retry_max_delay_seconds,
            llm_max_concurrency=self.llm_max_concurrency,
            ocr_max_concurrency=self.ocr_max_concurrency,
        )
        _ = self.api
        if self.environment is Environment.PROD:
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
    def minio(self) -> MinioSettings:
        return MinioSettings(
            endpoint=self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            bucket=self.minio_bucket,
            secure=self.minio_secure,
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
    def auth(self) -> AuthSettings:
        return AuthSettings(
            enabled=self.auth_enabled,
            algorithm=self.jwt_algorithm,
            signing_key=self.jwt_signing_key,
            issuer=self.jwt_issuer,
            audience=self.jwt_audience,
            access_token_ttl_seconds=self.jwt_access_token_ttl_seconds,
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
