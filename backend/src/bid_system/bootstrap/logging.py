"""Safe process logging configured explicitly during application startup."""

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime

from bid_system.platform.config import LoggingSettings
from bid_system.platform.config.secrets import redact_mapping, redact_text

REQUEST_LOG_FIELDS = (
    "request_id",
    "trace_id",
    "user_id",
    "tenant_id",
    "method",
    "path",
    "client_ip",
    "started_at",
    "status_code",
    "duration_ms",
)


class SensitiveDataFilter(logging.Filter):
    """Redact common credential forms before a record reaches any handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, Mapping) and all(
            isinstance(key, str) and isinstance(value, str) for key, value in record.msg.items()
        ):
            record.msg = redact_mapping(record.msg)
        elif isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        return True


class JsonFormatter(logging.Formatter):
    """Emit a minimal stable JSON log envelope."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str | int | float | None] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info is not None:
            # WHY: exception strings are untrusted and may contain credentials or provider payloads.
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        for field_name in REQUEST_LOG_FIELDS:
            field_value = getattr(record, field_name, None)
            if isinstance(field_value, (str, int, float)) or field_value is None:
                payload[field_name] = field_value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: LoggingSettings) -> None:
    """Configure root logging once the validated settings are available."""
    handler = logging.StreamHandler()
    handler.addFilter(SensitiveDataFilter())
    if settings.json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=settings.level.upper(), handlers=[handler], force=True)
