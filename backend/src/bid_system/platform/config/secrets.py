"""Compatibility exports for callers migrating to platform telemetry redaction."""

from collections.abc import Mapping

from bid_system.platform.telemetry.redaction import (
    REDACTED,
    SENSITIVE_KEY_PATTERN,
    redact_text,
)


def redact_mapping(value: Mapping[str, str]) -> dict[str, str]:
    """Preserve the original string-only configuration redaction contract."""
    return {
        key: REDACTED if SENSITIVE_KEY_PATTERN.search(key) else redact_text(item)
        for key, item in value.items()
    }


__all__ = ("REDACTED", "redact_mapping", "redact_text")
