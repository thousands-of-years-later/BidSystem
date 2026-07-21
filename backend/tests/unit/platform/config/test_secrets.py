"""Unit tests for configuration and log redaction helpers."""

from bid_system.platform.config.secrets import REDACTED, redact_mapping, redact_text


def test_redacts_sensitive_mapping_values_and_url_credentials() -> None:
    rendered = redact_mapping(
        {
            "authorization": "Bearer private-token",
            "JWT_SIGNING_KEY": "private-signing-key",
            "endpoint": "postgresql://user:private-password@localhost/database",
            "message": "safe",
        }
    )

    assert rendered["authorization"] == REDACTED
    assert rendered["JWT_SIGNING_KEY"] == REDACTED
    assert "private-password" not in rendered["endpoint"]
    assert rendered["message"] == "safe"


def test_redacts_sensitive_key_value_text() -> None:
    rendered = redact_text("JWT_SIGNING_KEY=private-key api_key=private-api-key")

    assert "private-key" not in rendered
    assert "private-api-key" not in rendered
    assert REDACTED in rendered
