"""Unit tests for deterministic configuration loading."""

from pathlib import Path

import pytest

from bid_system.platform.config.loader import ConfigurationLoadError, load_settings
from bid_system.platform.config.models import Environment


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


def test_environment_variables_override_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)
    monkeypatch.setenv("APP_ENV", "test")

    settings = load_settings(env_file)

    assert settings.environment is Environment.TEST


def test_reports_invalid_fields_without_secret_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)
    secret = "should-never-appear-in-the-error"
    with env_file.open("a", encoding="utf-8") as stream:
        stream.write(f"\nDATABASE_URL=https://user:{secret}@localhost/database\n")

    with pytest.raises(ConfigurationLoadError) as raised:
        load_settings(env_file)

    assert "database_url" in str(raised.value)
    assert secret not in str(raised.value)
    assert raised.value.issues


def test_missing_required_configuration_uses_stable_error(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=test\n", encoding="utf-8")

    with pytest.raises(ConfigurationLoadError) as raised:
        load_settings(env_file)

    assert {issue.field for issue in raised.value.issues} >= {
        "database_url",
        "redis_url",
        "minio_endpoint",
    }
