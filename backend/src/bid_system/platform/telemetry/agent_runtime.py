"""OpenTelemetry and structured-log adapters for Agent Runtime observability ports."""

import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from opentelemetry import trace
from opentelemetry.trace import Tracer

from bid_system.agent_runtime.core.agent import RunContext
from bid_system.agent_runtime.observability.events import RuntimeEvent
from bid_system.platform.telemetry.logging import LogChannel, get_logger

RUNTIME_TRACE_INSTRUMENTATION_NAME = "bid_system.agent_runtime"
TOOL_SPAN_PREFIX = "agent_runtime.tool"
RUNTIME_EVENT_PREFIX = "agent_runtime"


def _skill_versions(context: RunContext) -> str:
    return ",".join(
        f"{skill.name}@{skill.version}" for skill in context.versions.skills
    )


class OpenTelemetryRuntimeTracer:
    """Record tool-attempt spans without business documents or model content."""

    def __init__(self, tracer: Tracer | None = None) -> None:
        self._tracer = tracer or trace.get_tracer(RUNTIME_TRACE_INSTRUMENTATION_NAME)

    def start_tool_span(
        self,
        *,
        context: RunContext,
        tool_name: str,
        attempt: int,
    ) -> AbstractAsyncContextManager[None]:
        """Start one bounded span for a single tool attempt."""
        return self._tool_span(context=context, tool_name=tool_name, attempt=attempt)

    @asynccontextmanager
    async def _tool_span(
        self,
        *,
        context: RunContext,
        tool_name: str,
        attempt: int,
    ) -> AsyncIterator[None]:
        attributes: dict[str, str | int] = {
            "agent.run.id": context.identity.run_id,
            "agent.request.id": context.identity.request_id,
            "agent.trace.id": context.identity.trace_id,
            "agent.tool.name": tool_name,
            "agent.tool.attempt": attempt,
            "agent.model.name": context.versions.model_name,
            "agent.model.version": context.versions.model_version,
            "agent.prompt.name": context.versions.prompt_name,
            "agent.prompt.version": context.versions.prompt_version,
            "agent.skill.versions": _skill_versions(context),
        }
        if context.identity.task_id is not None:
            attributes["agent.task.id"] = context.identity.task_id
        if context.identity.tenant_id is not None:
            attributes["agent.tenant.id"] = context.identity.tenant_id
        if context.identity.actor_id is not None:
            attributes["agent.actor.id"] = context.identity.actor_id
        with self._tracer.start_as_current_span(
            f"{TOOL_SPAN_PREFIX}.{tool_name}",
            attributes=attributes,
        ):
            yield


class LoggingRuntimeEventRecorder:
    """Emit metadata-only runtime events through the redacting runtime logger."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or get_logger(LogChannel.RUNTIME, "agent_runtime")

    async def record(self, event: RuntimeEvent) -> None:
        """Write one bounded event without prompts, responses, or document payloads."""
        identity = event.context.identity
        versions = event.context.versions
        self._logger.info(
            event.event_type.value,
            extra={
                "event_name": f"{RUNTIME_EVENT_PREFIX}.{event.event_type.value}",
                "request_id": identity.request_id,
                "trace_id": identity.trace_id,
                "tenant_id": identity.tenant_id,
                "actor_id": identity.actor_id,
                "task_id": identity.task_id,
                "run_id": identity.run_id,
                "tool_name": event.tool_name,
                "attempt": event.attempt,
                "duration_ms": event.duration_ms,
                "retry_delay_seconds": event.retry_delay_seconds,
                "error_type": None if event.error_code is None else event.error_code.value,
                "model_name": versions.model_name,
                "model_version": versions.model_version,
                "prompt_name": versions.prompt_name,
                "prompt_version": versions.prompt_version,
                "skill_versions": _skill_versions(event.context),
            },
        )
