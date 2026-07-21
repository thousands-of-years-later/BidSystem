"""Deterministic application configuration loading."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from bid_system.platform.config.models import AppSettings

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


@dataclass(frozen=True)
class ConfigurationIssue:
    """Safe, stable description of one invalid configuration field."""

    field: str
    code: str


class ConfigurationLoadError(RuntimeError):
    """Raised when startup configuration cannot be validated safely."""

    def __init__(self, issues: tuple[ConfigurationIssue, ...]) -> None:
        self.issues = issues
        summary = ", ".join(f"{issue.field} ({issue.code})" for issue in issues)
        super().__init__(f"Application configuration validation failed: {summary}")


def load_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> AppSettings:
    """Load and validate settings without opening external resources or caching values."""
    try:
        return AppSettings(_env_file=env_file)
    except ValidationError as error:
        # WHY: Pydantic errors can include the rejected input, which may be a credential.
        issues = tuple(
            ConfigurationIssue(
                field=".".join(str(part).lower() for part in item["loc"]) or "configuration",
                code=str(item["type"]),
            )
            for item in error.errors(include_input=False, include_context=False, include_url=False)
        )
        raise ConfigurationLoadError(issues) from error
