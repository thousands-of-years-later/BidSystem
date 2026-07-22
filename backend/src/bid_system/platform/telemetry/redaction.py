"""Deterministic redaction for values that may reach telemetry sinks."""

import re
from collections.abc import Mapping, Sequence

REDACTED = "***"
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:authorization|cookie|api[_-]?key|access[_-]?key|password|secret|token|"
    r"signing[_-]?key|private[_-]?key|database_url|redis_url)",
    re.IGNORECASE,
)
URL_CREDENTIAL_PATTERN = re.compile(r"(?P<prefix>://[^:/\s]+:)[^@\s]+@")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?P<key>authorization|cookie|api[_-]?key|access[_-]?key|password|secret|token|"
    r"signing[_-]?key|private[_-]?key|database_url|redis_url)"
    r"(?P<value>\s*[:=]\s*(?:Bearer\s+)?[^\s,;]+)?",
    re.IGNORECASE,
)

type ScalarValue = str | int | float | bool | None
type RedactableValue = ScalarValue | Mapping[str, RedactableValue] | Sequence[RedactableValue]


def redact_text(value: str) -> str:
    """Remove URL credentials and common inline credential forms."""
    without_url_credentials = URL_CREDENTIAL_PATTERN.sub(rf"\g<prefix>{REDACTED}@", value)
    return SENSITIVE_TEXT_PATTERN.sub(REDACTED, without_url_credentials)


def redact_value(value: RedactableValue) -> RedactableValue:
    """Return a recursively redacted copy of a telemetry-safe value."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, Sequence):
        return [redact_value(item) for item in value]
    return value


def redact_mapping(value: Mapping[str, RedactableValue]) -> dict[str, RedactableValue]:
    """Return a copy whose sensitive keys and nested values are redacted."""
    return {
        key: REDACTED if SENSITIVE_KEY_PATTERN.search(key) else redact_value(item)
        for key, item in value.items()
    }
