"""Unit tests for validated application settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from bid_system.bootstrap.settings import Environment, load_settings


def _write_env(path: Path, *, environment: str = "dev") -> None:
    path.write_text(
        "\n".join(
            (
                f"APP_ENV={environment}",
                "DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/bid_system",
                "REDIS_URL=redis://localhost:6379/0",
                "MINIO_ENDPOINT=localhost:9000",
                "MINIO_ACCESS_KEY=access-key",
                "MINIO_SECRET_KEY=secret-key",
                "MINIO_BUCKET=bid-system",
            )
        ),
        encoding="utf-8",
    )


def test_loads_dotenv_and_environment_variables_take_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)
    monkeypatch.setenv("APP_ENV", "test")

    settings = load_settings(env_file)

    assert settings.environment is Environment.TEST
    assert settings.database.url.get_secret_value().endswith("/bid_system")
    assert settings.minio.bucket == "bid-system"


def test_rejects_invalid_pool_and_timeout_boundaries(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)
    with env_file.open("a", encoding="utf-8") as stream:
        stream.write("\nDATABASE_POOL_SIZE=0\nHTTP_TIMEOUT_SECONDS=0\n")

    with pytest.raises(ValidationError):
        load_settings(env_file)


def test_prod_requires_enabled_provider_credentials(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, environment="prod")
    with env_file.open("a", encoding="utf-8") as stream:
        stream.write("\nLLM_ENABLED=true\nLLM_BASE_URL=https://llm.example.test/v1\n")

    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        load_settings(env_file)


def test_enabled_provider_rejects_blank_credentials(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)
    with env_file.open("a", encoding="utf-8") as stream:
        stream.write(
            "\nLLM_ENABLED=true\nLLM_BASE_URL=https://llm.example.test/v1"
            "\nLLM_API_KEY=\nLLM_MODEL=\n"
        )

    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        load_settings(env_file)


def test_rejects_unsupported_database_and_redis_schemes(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)
    with env_file.open("a", encoding="utf-8") as stream:
        stream.write("\nDATABASE_URL=https://localhost/db\nREDIS_URL=https://localhost/redis\n")

    with pytest.raises(ValidationError):
        load_settings(env_file)


def test_secret_values_are_not_exposed_by_repr(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)

    rendered = repr(load_settings(env_file))

    assert "password" not in rendered
    assert "secret-key" not in rendered


def test_api_settings_have_safe_environment_aware_defaults(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)

    settings = load_settings(env_file)

    assert settings.api.prefix == "/api/v1"
    assert settings.api.docs_enabled is True
    assert settings.api.trusted_hosts == ("localhost", "testserver")
    assert settings.api.max_request_body_bytes > 0


def test_production_disables_api_documentation(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, environment="prod")

    settings = load_settings(env_file)

    assert settings.api.docs_enabled is False


def test_rejects_invalid_api_limits(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)
    with env_file.open("a", encoding="utf-8") as stream:
        stream.write("\nAPI_MAX_REQUEST_BODY_BYTES=0\nAPI_READINESS_TIMEOUT_SECONDS=0\n")

    with pytest.raises(ValidationError):
        load_settings(env_file)
