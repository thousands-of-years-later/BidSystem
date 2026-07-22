"""Trace port isolated from OpenTelemetry and other provider implementations."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

from bid_system.agent_runtime.context.run import RunContext


class RuntimeTracer(Protocol):
    """Port for tracing a single tool attempt."""

    def start_tool_span(
        self,
        *,
        context: RunContext,
        tool_name: str,
        attempt: int,
    ) -> AbstractAsyncContextManager[None]: ...


@asynccontextmanager
async def _no_op_span() -> AsyncIterator[None]:
    yield


class NoOpRuntimeTracer:
    """Default tracer used when trace export is not configured."""

    def start_tool_span(
        self,
        *,
        context: RunContext,
        tool_name: str,
        attempt: int,
    ) -> AbstractAsyncContextManager[None]:
        """Return an async span boundary without external side effects."""
        return _no_op_span()
