"""Structured process logging with separate runtime and audit channels."""

import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import TracebackType

from bid_system.platform.config import LoggingSettings
from bid_system.platform.telemetry.redaction import redact_mapping, redact_text
from bid_system.platform.telemetry.tracing import current_correlation_context

DEFAULT_SERVICE_NAME = "bid-system"
DEFAULT_ENVIRONMENT = "unknown"
RUNTIME_LOGGER_NAME = "bid_system.runtime"
AUDIT_LOGGER_NAME = "bid_system.audit"
LOG_FIELDS = (
    "event_name",
    "request_id",
    "trace_id",
    "span_id",
    "tenant_id",
    "user_id",
    "task_id",
    "task_name",
    "run_id",
    "tool_name",
    "attempt",
    "retry_delay_seconds",
    "model_name",
    "model_version",
    "prompt_name",
    "prompt_version",
    "skill_versions",
    "method",
    "route",
    "path",
    "client_ip",
    "status_code",
    "duration_ms",
    "outcome",
    "error_type",
    "provider",
    "operation",
    "queue_name",
    "action",
    "actor_id",
    "target_type",
    "target_id",
)
type ExceptionInfo = (
    tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
)


class LogChannel(StrEnum):
    """Process log streams with distinct retention and access policies."""

    RUNTIME = "runtime"
    AUDIT = "audit"


@dataclass(frozen=True)
class AuditEvent:
    """Sanitized operational audit event; not a substitute for a domain audit record."""

    event_name: str
    action: str
    actor_id: str | None
    target_type: str
    target_id: str
    outcome: str


class SensitiveDataFilter(logging.Filter):
    """Redact common credential forms before a record reaches any handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        correlation = current_correlation_context()
        if correlation is not None:
            if not hasattr(record, "request_id"):
                record.request_id = correlation.request_id
            if not hasattr(record, "trace_id"):
                record.trace_id = correlation.trace_id
            if not hasattr(record, "span_id"):
                record.span_id = correlation.span_id
        if isinstance(record.msg, dict) and all(isinstance(key, str) for key in record.msg):
            record.msg = redact_mapping(record.msg)
        elif isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        return True


class ExcludeAuditFilter(logging.Filter):
    """Prevent audit records from propagating into the runtime stream."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(AUDIT_LOGGER_NAME)


class JsonFormatter(logging.Formatter):
    """Emit a stable JSON envelope without uncontrolled record attributes."""

    def __init__(
        self,
        *,
        service_name: str = DEFAULT_SERVICE_NAME,
        environment: str = DEFAULT_ENVIRONMENT,
    ) -> None:
        super().__init__()
        self._service_name = service_name
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str | int | float | bool | None] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "service_name": self._service_name,
            "environment": self._environment,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "log_type": (
                LogChannel.AUDIT.value
                if record.name.startswith(AUDIT_LOGGER_NAME)
                else LogChannel.RUNTIME.value
            ),
        }
        for field_name in LOG_FIELDS:
            field_value = getattr(record, field_name, None)
            if isinstance(field_value, str):
                payload[field_name] = redact_text(field_value)
            elif isinstance(field_value, (int, float, bool)) or field_value is None:
                payload[field_name] = field_value
        if record.exc_info is not None:
            # WHY: provider and driver exceptions may contain credentials or submitted content.
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class RedactingTextFormatter(logging.Formatter):
    """Keep developer-readable logs subject to the same redaction guarantees."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))

    def formatException(self, exc_info: ExceptionInfo) -> str:
        return redact_text(super().formatException(exc_info))


def get_logger(channel: LogChannel, component: str) -> logging.Logger:
    """Return a logger in an explicitly selected retention channel."""
    base_name = RUNTIME_LOGGER_NAME if channel is LogChannel.RUNTIME else AUDIT_LOGGER_NAME
    return logging.getLogger(f"{base_name}.{component}")


def emit_audit_event(component: str, event: AuditEvent) -> None:
    """Emit metadata-only audit telemetry to the isolated audit channel."""
    get_logger(LogChannel.AUDIT, component).info(
        event.event_name,
        extra={
            "event_name": event.event_name,
            "action": event.action,
            "actor_id": event.actor_id,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "outcome": event.outcome,
        },
    )


def configure_logging(
    settings: LoggingSettings,
    *,
    service_name: str = DEFAULT_SERVICE_NAME,
    environment: str = DEFAULT_ENVIRONMENT,
) -> None:
    """Configure runtime stderr and audit stdout streams after settings validation."""
    formatter: logging.Formatter
    if settings.json_output:
        formatter = JsonFormatter(service_name=service_name, environment=environment)
    else:
        formatter = RedactingTextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    runtime_handler = logging.StreamHandler(sys.stderr)
    runtime_handler.setFormatter(formatter)
    runtime_handler.addFilter(SensitiveDataFilter())
    runtime_handler.addFilter(ExcludeAuditFilter())

    audit_handler = logging.StreamHandler(sys.stdout)
    audit_handler.setFormatter(formatter)
    audit_handler.addFilter(SensitiveDataFilter())

    root_logger = logging.getLogger()
    root_logger.handlers = [runtime_handler]
    root_logger.setLevel(settings.level)

    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.handlers = [audit_handler]
    audit_logger.setLevel(settings.level)
    audit_logger.propagate = False
