"""Telemetry redaction behavior tests."""

from bid_system.platform.telemetry.redaction import (
    REDACTED,
    RedactableValue,
    redact_mapping,
    redact_text,
)


def test_redact_mapping_recurses_through_nested_payloads() -> None:
    payload: dict[str, RedactableValue] = {
        "authorization": "Bearer private-token",
        "request": {
            "headers": {"X-API-Key": "private-key", "accept": "application/json"},
            "items": ["safe", "password=private-password"],
        },
    }

    redacted = redact_mapping(payload)

    assert redacted["authorization"] == REDACTED
    assert redacted["request"] == {
        "headers": {"X-API-Key": REDACTED, "accept": "application/json"},
        "items": ["safe", REDACTED],
    }


def test_redact_text_hides_url_credentials_and_inline_secrets() -> None:
    rendered = redact_text(
        "database_url=postgresql://user:password@localhost/db token=private-token"
    )

    assert "password" not in rendered
    assert "private-token" not in rendered
    assert REDACTED in rendered
