"""Public telemetry primitives shared by platform adapters and process entrypoints."""

from bid_system.platform.telemetry.agent_runtime import (
    LoggingRuntimeEventRecorder,
    OpenTelemetryRuntimeTracer,
)
from bid_system.platform.telemetry.logging import (
    AuditEvent,
    LogChannel,
    configure_logging,
    emit_audit_event,
    get_logger,
)

__all__ = (
    "AuditEvent",
    "LogChannel",
    "LoggingRuntimeEventRecorder",
    "OpenTelemetryRuntimeTracer",
    "configure_logging",
    "emit_audit_event",
    "get_logger",
)
