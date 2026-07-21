"""Credential redaction helpers shared by configuration and process logging."""

import re
from collections.abc import Mapping

REDACTED = "***"
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:authorization|api[_-]?key|access[_-]?key|password|secret|token|"
    r"signing[_-]?key|private[_-]?key|database_url|redis_url)",
    re.IGNORECASE,
)
URL_CREDENTIAL_PATTERN = re.compile(r"(?P<prefix>://[^:/\s]+:)[^@\s]+@")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?P<key>authorization|api[_-]?key|access[_-]?key|password|secret|token|"
    r"signing[_-]?key|private[_-]?key|database_url|redis_url)"
    r"(?P<value>\s*[:=]\s*[^\s,;]+)?",
    re.IGNORECASE,
)


def redact_text(value: str) -> str:
    """Remove URL credentials and common inline credential forms."""
    without_url_credentials = URL_CREDENTIAL_PATTERN.sub(rf"\g<prefix>{REDACTED}@", value)
    return SENSITIVE_TEXT_PATTERN.sub(REDACTED, without_url_credentials)


def redact_mapping(value: Mapping[str, str]) -> dict[str, str]:
    """Return a copy whose sensitive values cannot reach a log handler."""
    return {
        key: REDACTED if SENSITIVE_KEY_PATTERN.search(key) else redact_text(item)
        for key, item in value.items()
    }
