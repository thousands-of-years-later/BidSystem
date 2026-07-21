"""Validated settings loaded explicitly at the application boundary."""

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
DEFAULT_DATABASE_POOL_SIZE = 5
DEFAULT_DATABASE_MAX_OVERFLOW = 10
DEFAULT_DATABASE_POOL_TIMEOUT_SECONDS = 30.0
DEFAULT_REDIS_MAX_CONNECTIONS = 20
DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_STARTUP_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0
DEFAULT_GZIP_MINIMUM_SIZE_BYTES = 1024
DEFAULT_MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024
DEFAULT_READINESS_TIMEOUT_SECONDS = 3.0
DEFAULT_API_TITLE = "Bid System API"
DEFAULT_API_DESCRIPTION = "HTTP API for the bid agent platform."
DEFAULT_API_PREFIX = "/api/v1"
DEFAULT_TRUSTED_HOSTS = ("localhost", "testserver")


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


class AppSettings(BaseSettings):
    """Root settings model; environment variables override the dotenv source."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Field(
        default=Environment.DEV,
        validation_alias="APP_ENV",
    )
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
    api_title: str = Field(default=DEFAULT_API_TITLE, validation_alias="API_TITLE")
    api_description: str = Field(
        default=DEFAULT_API_DESCRIPTION,
        validation_alias="API_DESCRIPTION",
    )
    api_prefix: str = Field(default=DEFAULT_API_PREFIX, validation_alias="API_PREFIX")
    api_cors_origins: tuple[str, ...] = Field(
        default=(),
        validation_alias="API_CORS_ORIGINS",
    )
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

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> Self:
        """Require complete credentials only when an external provider is enabled."""
        llm_api_key = None if self.llm_api_key is None else self.llm_api_key.get_secret_value()
        ocr_api_key = None if self.ocr_api_key is None else self.ocr_api_key.get_secret_value()
        if self.llm_enabled and not (self.llm_base_url and llm_api_key and self.llm_model):
            raise ValueError("LLM_BASE_URL, LLM_API_KEY and LLM_MODEL are required when enabled")
        if self.ocr_enabled and not (self.ocr_base_url and ocr_api_key and self.ocr_model):
            raise ValueError("OCR_BASE_URL, OCR_API_KEY and OCR_MODEL are required when enabled")
        return self

    @property
    def database(self) -> DatabaseSettings:
        """Return the cohesive PostgreSQL settings view."""
        return DatabaseSettings(
            url=self.database_url,
            pool_size=self.database_pool_size,
            max_overflow=self.database_max_overflow,
            pool_timeout_seconds=self.database_pool_timeout_seconds,
        )

    @property
    def redis(self) -> RedisSettings:
        """Return the cohesive Redis settings view."""
        return RedisSettings(url=self.redis_url, max_connections=self.redis_max_connections)

    @property
    def minio(self) -> MinioSettings:
        """Return the cohesive MinIO settings view."""
        return MinioSettings(
            endpoint=self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            bucket=self.minio_bucket,
            secure=self.minio_secure,
        )

    @property
    def llm(self) -> ProviderSettings:
        """Return the LLM provider settings view."""
        return ProviderSettings(
            enabled=self.llm_enabled,
            base_url=self.llm_base_url,
            api_key=self.llm_api_key,
            model=self.llm_model,
            probe_on_startup=self.llm_probe_on_startup,
        )

    @property
    def ocr(self) -> ProviderSettings:
        """Return the OCR provider settings view."""
        return ProviderSettings(
            enabled=self.ocr_enabled,
            base_url=self.ocr_base_url,
            api_key=self.ocr_api_key,
            model=self.ocr_model,
            probe_on_startup=self.ocr_probe_on_startup,
        )

    @property
    def startup(self) -> StartupSettings:
        """Return startup and shutdown settings."""
        return StartupSettings(
            connect_timeout_seconds=self.startup_connect_timeout_seconds,
            shutdown_timeout_seconds=self.shutdown_timeout_seconds,
        )

    @property
    def logging(self) -> LoggingSettings:
        """Return logging settings."""
        return LoggingSettings(level=self.log_level, json_output=self.log_json)

    @property
    def api(self) -> ApiSettings:
        """Return HTTP settings with production documentation disabled."""
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


def load_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> AppSettings:
    """Load settings without caching so tests and process factories remain deterministic."""
    return AppSettings(_env_file=env_file)
