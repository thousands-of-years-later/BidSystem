import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from pydantic import BaseModel, ConfigDict

from bid_system.agent_runtime.context.run import RunContext, RunIdentity, RuntimeVersions
from bid_system.agent_runtime.observability.events import RuntimeEvent, RuntimeEventType
from bid_system.agent_runtime.tools.base import ToolSpec
from bid_system.agent_runtime.tools.executor import ToolExecutor
from bid_system.agent_runtime.tools.registry import ToolRegistry
from bid_system.agent_runtime.tools.response import ToolError, ToolErrorCode, ToolResponse


class ExecutorInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str


class ExecutorOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str


class WrongOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str


class RecordingEvents:
    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    async def record(self, event: RuntimeEvent) -> None:
        self.events.append(event)


class RecordingTracer:
    def __init__(self) -> None:
        self.attempts: list[int] = []

    @asynccontextmanager
    async def start_tool_span(
        self,
        *,
        context: RunContext,
        tool_name: str,
        attempt: int,
    ) -> AsyncIterator[None]:
        self.attempts.append(attempt)
        yield


class SequenceTool:
    input_schema = ExecutorInput
    output_schema = ExecutorOutput

    def __init__(self, spec: ToolSpec, responses: list[ToolResponse[BaseModel]]) -> None:
        self.spec = spec
        self._responses = responses
        self.invocations = 0

    async def invoke(
        self,
        input_data: BaseModel,
        context: RunContext,
    ) -> ToolResponse[BaseModel]:
        self.invocations += 1
        return self._responses.pop(0)


class BlockingTool:
    input_schema = ExecutorInput
    output_schema = ExecutorOutput

    def __init__(self, spec: ToolSpec) -> None:
        self.spec = spec
        self.invocations = 0
        self._never_set = asyncio.Event()

    async def invoke(
        self,
        input_data: BaseModel,
        context: RunContext,
    ) -> ToolResponse[BaseModel]:
        self.invocations += 1
        await self._never_set.wait()
        return ToolResponse.success(ExecutorOutput(candidate_id="unreachable"))


class CancellingTool:
    input_schema = ExecutorInput
    output_schema = ExecutorOutput
    spec = ToolSpec(name="cancel", timeout_seconds=1.0)

    async def invoke(
        self,
        input_data: BaseModel,
        context: RunContext,
    ) -> ToolResponse[BaseModel]:
        raise asyncio.CancelledError


class FailingTool:
    input_schema = ExecutorInput
    output_schema = ExecutorOutput
    spec = ToolSpec(name="fail", timeout_seconds=1.0)

    async def invoke(
        self,
        input_data: BaseModel,
        context: RunContext,
    ) -> ToolResponse[BaseModel]:
        raise RuntimeError("secret provider detail")


def _context() -> RunContext:
    return RunContext(
        identity=RunIdentity(run_id="run-1", request_id="request-1", trace_id="1" * 32),
        versions=RuntimeVersions(
            model_name="extractor",
            model_version="2026-07-01",
            prompt_name="product-fact-extract",
            prompt_version="v1",
        ),
    )


def _executor(
    tool: SequenceTool | BlockingTool | CancellingTool | FailingTool,
    events: RecordingEvents,
    tracer: RecordingTracer,
    delays: list[float],
) -> ToolExecutor:
    registry = ToolRegistry()
    registry.register(tool)

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    return ToolExecutor(
        registry,
        event_recorder=events,
        tracer=tracer,
        sleeper=record_delay,
    )


@pytest.mark.asyncio
async def test_executor_returns_success_and_records_trace_and_events() -> None:
    tool = SequenceTool(
        ToolSpec(name="extract", timeout_seconds=1.0),
        [ToolResponse.success(ExecutorOutput(candidate_id="candidate-1"))],
    )
    events = RecordingEvents()
    tracer = RecordingTracer()
    executor = _executor(tool, events, tracer, [])

    response = await executor.execute("extract", ExecutorInput(source_id="source-1"), _context())

    assert response.is_success
    assert response.value == ExecutorOutput(candidate_id="candidate-1")
    assert tracer.attempts == [1]
    assert [event.event_type for event in events.events] == [
        RuntimeEventType.TOOL_STARTED,
        RuntimeEventType.TOOL_SUCCEEDED,
    ]


@pytest.mark.asyncio
async def test_executor_retries_only_retryable_idempotent_failure() -> None:
    tool = SequenceTool(
        ToolSpec(
            name="extract",
            timeout_seconds=1.0,
            max_attempts=3,
            retry_base_delay_seconds=0.25,
            retry_max_delay_seconds=1.0,
            idempotent=True,
        ),
        [
            ToolResponse.failure(
                ToolError(
                    code=ToolErrorCode.UNAVAILABLE,
                    message="parser unavailable",
                    retryable=True,
                )
            ),
            ToolResponse.success(ExecutorOutput(candidate_id="candidate-1")),
        ],
    )
    events = RecordingEvents()
    tracer = RecordingTracer()
    delays: list[float] = []
    executor = _executor(tool, events, tracer, delays)

    response = await executor.execute("extract", ExecutorInput(source_id="source-1"), _context())

    assert response.is_success
    assert tool.invocations == 2
    assert delays == [0.25]
    assert RuntimeEventType.TOOL_RETRYING in [event.event_type for event in events.events]


@pytest.mark.asyncio
async def test_executor_does_not_retry_non_idempotent_tool() -> None:
    tool = SequenceTool(
        ToolSpec(name="publish", timeout_seconds=1.0, max_attempts=3, idempotent=False),
        [
            ToolResponse.failure(
                ToolError(
                    code=ToolErrorCode.UNAVAILABLE,
                    message="publisher unavailable",
                    retryable=True,
                )
            )
        ],
    )
    events = RecordingEvents()
    executor = _executor(tool, events, RecordingTracer(), [])

    response = await executor.execute("publish", ExecutorInput(source_id="source-1"), _context())

    assert not response.is_success
    assert tool.invocations == 1
    assert RuntimeEventType.TOOL_RETRYING not in [event.event_type for event in events.events]


@pytest.mark.asyncio
async def test_executor_bounds_timeout_retries() -> None:
    tool = BlockingTool(
        ToolSpec(
            name="extract",
            timeout_seconds=0.01,
            max_attempts=2,
            retry_base_delay_seconds=0.01,
            retry_max_delay_seconds=0.01,
            idempotent=True,
        )
    )
    events = RecordingEvents()
    delays: list[float] = []
    executor = _executor(tool, events, RecordingTracer(), delays)

    response = await executor.execute("extract", ExecutorInput(source_id="source-1"), _context())

    assert response.error is not None
    assert response.error.code is ToolErrorCode.TIMEOUT
    assert tool.invocations == 2
    assert delays == [0.01]
    assert [event.event_type for event in events.events].count(
        RuntimeEventType.TOOL_TIMED_OUT
    ) == 2


@pytest.mark.asyncio
async def test_executor_rejects_wrong_input_without_invoking_tool() -> None:
    tool = SequenceTool(
        ToolSpec(name="extract", timeout_seconds=1.0),
        [ToolResponse.success(ExecutorOutput(candidate_id="candidate-1"))],
    )
    executor = _executor(tool, RecordingEvents(), RecordingTracer(), [])

    response = await executor.execute(
        "extract",
        WrongOutput(reason="wrong schema"),
        _context(),
    )

    assert response.error is not None
    assert response.error.code is ToolErrorCode.INVALID_INPUT
    assert tool.invocations == 0


@pytest.mark.asyncio
async def test_executor_rejects_output_outside_registered_schema() -> None:
    tool = SequenceTool(
        ToolSpec(name="extract", timeout_seconds=1.0),
        [ToolResponse.success(WrongOutput(reason="wrong schema"))],
    )
    executor = _executor(tool, RecordingEvents(), RecordingTracer(), [])

    response = await executor.execute(
        "extract",
        ExecutorInput(source_id="source-1"),
        _context(),
    )

    assert response.error is not None
    assert response.error.code is ToolErrorCode.EXECUTION_FAILED


@pytest.mark.asyncio
async def test_executor_maps_unknown_exception_without_leaking_detail() -> None:
    executor = _executor(FailingTool(), RecordingEvents(), RecordingTracer(), [])

    response = await executor.execute(
        "fail",
        ExecutorInput(source_id="source-1"),
        _context(),
    )

    assert response.error is not None
    assert response.error.code is ToolErrorCode.EXECUTION_FAILED
    assert "secret provider detail" not in response.error.message


@pytest.mark.asyncio
async def test_executor_propagates_cancellation() -> None:
    executor = _executor(CancellingTool(), RecordingEvents(), RecordingTracer(), [])

    with pytest.raises(asyncio.CancelledError):
        await executor.execute("cancel", ExecutorInput(source_id="source-1"), _context())
