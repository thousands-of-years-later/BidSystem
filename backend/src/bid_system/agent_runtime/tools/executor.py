"""Bounded tool execution with timeout, safe failure mapping, and finite retry."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import monotonic

from pydantic import BaseModel

from bid_system.agent_runtime.core.agent import RunContext
from bid_system.agent_runtime.observability.events import (
    NoOpRuntimeEventRecorder,
    RuntimeEvent,
    RuntimeEventRecorder,
    RuntimeEventType,
)
from bid_system.agent_runtime.observability.traces import NoOpRuntimeTracer, RuntimeTracer
from bid_system.agent_runtime.tools.base import Tool, ToolSpec
from bid_system.agent_runtime.tools.registry import ToolRegistry
from bid_system.agent_runtime.tools.response import ToolError, ToolErrorCode, ToolResponse

MILLISECONDS_PER_SECOND = 1_000.0
BACKOFF_MULTIPLIER = 2.0
TOOL_TIMEOUT_MESSAGE = "Tool execution timed out"
TOOL_EXECUTION_FAILURE_MESSAGE = "Tool execution failed"
TOOL_INPUT_SCHEMA_MESSAGE = "Tool input does not match the registered schema"
TOOL_OUTPUT_SCHEMA_MESSAGE = "Tool output does not match the registered schema"

Sleeper = Callable[[float], Awaitable[None]]
MonotonicClock = Callable[[], float]
UtcClock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ToolExecutor:
    """Execute registered tools without allowing unbounded retries or waits."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        event_recorder: RuntimeEventRecorder | None = None,
        tracer: RuntimeTracer | None = None,
        sleeper: Sleeper = asyncio.sleep,
        monotonic_clock: MonotonicClock = monotonic,
        utc_clock: UtcClock = _utc_now,
    ) -> None:
        self._registry = registry
        self._event_recorder = event_recorder or NoOpRuntimeEventRecorder()
        self._tracer = tracer or NoOpRuntimeTracer()
        self._sleeper = sleeper
        self._monotonic_clock = monotonic_clock
        self._utc_clock = utc_clock

    async def execute(
        self,
        tool_name: str,
        input_data: BaseModel,
        context: RunContext,
    ) -> ToolResponse[BaseModel]:
        """Execute one registered tool according to its immutable policy."""
        tool = self._registry.get(tool_name)
        if not isinstance(input_data, tool.input_schema):
            return ToolResponse.failure(
                ToolError(
                    code=ToolErrorCode.INVALID_INPUT,
                    message=TOOL_INPUT_SCHEMA_MESSAGE,
                )
            )

        for attempt in range(1, tool.spec.max_attempts + 1):
            await self._record(
                event_type=RuntimeEventType.TOOL_STARTED,
                context=context,
                tool=tool,
                attempt=attempt,
                duration_ms=0.0,
            )
            started_at = self._monotonic_clock()
            response, terminal_event = await self._invoke_attempt(
                tool=tool,
                input_data=input_data,
                context=context,
                attempt=attempt,
            )
            duration_ms = max(
                0.0,
                (self._monotonic_clock() - started_at) * MILLISECONDS_PER_SECOND,
            )
            error = response.error
            await self._record(
                event_type=terminal_event,
                context=context,
                tool=tool,
                attempt=attempt,
                duration_ms=duration_ms,
                error_code=None if error is None else error.code,
            )
            if response.is_success:
                return response
            if error is None or not self._should_retry(tool.spec, error, attempt):
                return response

            retry_delay = self._retry_delay(tool.spec, attempt)
            await self._record(
                event_type=RuntimeEventType.TOOL_RETRYING,
                context=context,
                tool=tool,
                attempt=attempt,
                duration_ms=duration_ms,
                error_code=error.code,
                retry_delay_seconds=retry_delay,
            )
            await self._sleeper(retry_delay)

        raise RuntimeError("Tool execution exhausted an unreachable control path")

    async def _invoke_attempt(
        self,
        *,
        tool: Tool,
        input_data: BaseModel,
        context: RunContext,
        attempt: int,
    ) -> tuple[ToolResponse[BaseModel], RuntimeEventType]:
        try:
            async with self._tracer.start_tool_span(
                context=context,
                tool_name=tool.spec.name,
                attempt=attempt,
            ):
                async with asyncio.timeout(tool.spec.timeout_seconds):
                    response = await tool.invoke(input_data, context)
        except TimeoutError:
            return (
                ToolResponse.failure(
                    ToolError(
                        code=ToolErrorCode.TIMEOUT,
                        message=TOOL_TIMEOUT_MESSAGE,
                        retryable=True,
                    )
                ),
                RuntimeEventType.TOOL_TIMED_OUT,
            )
        except Exception:
            # WHY: provider exceptions may contain submitted content or credentials.
            return (
                ToolResponse.failure(
                    ToolError(
                        code=ToolErrorCode.EXECUTION_FAILED,
                        message=TOOL_EXECUTION_FAILURE_MESSAGE,
                    )
                ),
                RuntimeEventType.TOOL_FAILED,
            )

        if response.value is not None and not isinstance(response.value, tool.output_schema):
            return (
                ToolResponse.failure(
                    ToolError(
                        code=ToolErrorCode.EXECUTION_FAILED,
                        message=TOOL_OUTPUT_SCHEMA_MESSAGE,
                    )
                ),
                RuntimeEventType.TOOL_FAILED,
            )
        event_type = (
            RuntimeEventType.TOOL_SUCCEEDED
            if response.is_success
            else RuntimeEventType.TOOL_FAILED
        )
        return response, event_type

    @staticmethod
    def _should_retry(spec: ToolSpec, error: ToolError, attempt: int) -> bool:
        return spec.idempotent and error.retryable and attempt < spec.max_attempts

    @staticmethod
    def _retry_delay(spec: ToolSpec, attempt: int) -> float:
        uncapped_delay = spec.retry_base_delay_seconds * BACKOFF_MULTIPLIER ** (attempt - 1)
        return min(uncapped_delay, spec.retry_max_delay_seconds)

    async def _record(
        self,
        *,
        event_type: RuntimeEventType,
        context: RunContext,
        tool: Tool,
        attempt: int,
        duration_ms: float,
        error_code: ToolErrorCode | None = None,
        retry_delay_seconds: float | None = None,
    ) -> None:
        await self._event_recorder.record(
            RuntimeEvent(
                event_type=event_type,
                occurred_at=self._utc_clock(),
                context=context,
                tool_name=tool.spec.name,
                attempt=attempt,
                duration_ms=duration_ms,
                error_code=error_code,
                retry_delay_seconds=retry_delay_seconds,
            )
        )
