"""Security-boundary facade over the single telemetry redaction implementation."""

from collections.abc import Mapping

from bid_system.platform.telemetry.redaction import (
    REDACTED,
    RedactableValue,
    redact_mapping,
    redact_text,
    redact_value,
)


def redact_response(value: Mapping[str, RedactableValue]) -> dict[str, RedactableValue]:
    """Return a recursively sanitized copy safe for a response or audit payload."""
    return redact_mapping(value)


__all__ = (
    "REDACTED",
    "redact_response",
    "redact_text",
    "redact_value",
)
