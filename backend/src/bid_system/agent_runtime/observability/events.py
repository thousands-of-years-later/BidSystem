"""Metadata-only runtime events with immutable provenance."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from bid_system.agent_runtime.context.run import RunContext
from bid_system.agent_runtime.tools.response import ToolErrorCode


class RuntimeEventType(StrEnum):
    """Stable lifecycle events emitted around tool execution."""

    TOOL_STARTED = "tool_started"
    TOOL_SUCCEEDED = "tool_succeeded"
    TOOL_RETRYING = "tool_retrying"
    TOOL_FAILED = "tool_failed"
    TOOL_TIMED_OUT = "tool_timed_out"


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """Bounded operational metadata that excludes prompts and business payloads."""

    event_type: RuntimeEventType
    occurred_at: datetime
    context: RunContext
    tool_name: str
    attempt: int
    duration_ms: float
    error_code: ToolErrorCode | None = None
    retry_delay_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.tool_name.strip():
            raise ValueError("tool_name must not be blank")
        if self.attempt < 1:
            raise ValueError("attempt must be at least one")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        if self.retry_delay_seconds is not None and self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")


class RuntimeEventRecorder(Protocol):
    """Port for persisting or emitting bounded runtime events."""

    async def record(self, event: RuntimeEvent) -> None: ...


class NoOpRuntimeEventRecorder:
    """Default recorder used when runtime event export is not configured."""

    async def record(self, event: RuntimeEvent) -> None:
        """Accept the event without external side effects."""
