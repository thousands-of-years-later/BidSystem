import logging
from datetime import UTC, datetime

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from bid_system.agent_runtime.context.run import (
    RunContext,
    RunIdentity,
    RuntimeVersions,
    SkillVersion,
)
from bid_system.agent_runtime.observability.events import RuntimeEvent, RuntimeEventType
from bid_system.platform.telemetry.agent_runtime import (
    LoggingRuntimeEventRecorder,
    OpenTelemetryRuntimeTracer,
)


def _context() -> RunContext:
    return RunContext(
        identity=RunIdentity(
            run_id="run-1",
            request_id="request-1",
            trace_id="1" * 32,
            task_id="task-1",
            tenant_id="tenant-1",
            actor_id="user-1",
        ),
        versions=RuntimeVersions(
            model_name="extractor",
            model_version="2026-07-01",
            prompt_name="product-fact-extract",
            prompt_version="v1",
            skills=(SkillVersion(name="fact-extraction", version="v2"),),
        ),
    )


@pytest.mark.asyncio
async def test_runtime_tracer_records_bounded_identity_and_version_attributes() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = OpenTelemetryRuntimeTracer(provider.get_tracer("test"))

    async with tracer.start_tool_span(
        context=_context(),
        tool_name="extract_document",
        attempt=1,
    ):
        pass

    span = exporter.get_finished_spans()[0]
    attributes = span.attributes
    assert attributes is not None
    assert span.name == "agent_runtime.tool.extract_document"
    assert attributes["agent.run.id"] == "run-1"
    assert attributes["agent.model.version"] == "2026-07-01"
    assert attributes["agent.prompt.version"] == "v1"
    assert attributes["agent.skill.versions"] == "fact-extraction@v2"
    assert "prompt" not in attributes
    assert "response" not in attributes


@pytest.mark.asyncio
async def test_runtime_event_recorder_emits_metadata_only_log_record() -> None:
    logger = logging.Logger("test.agent_runtime")
    records: list[logging.LogRecord] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger.addHandler(CaptureHandler())
    recorder = LoggingRuntimeEventRecorder(logger)
    event = RuntimeEvent(
        event_type=RuntimeEventType.TOOL_SUCCEEDED,
        occurred_at=datetime(2026, 7, 22, tzinfo=UTC),
        context=_context(),
        tool_name="extract_document",
        attempt=1,
        duration_ms=12.5,
    )

    await recorder.record(event)

    record = records[0]
    assert record.__dict__["event_name"] == "agent_runtime.tool_succeeded"
    assert record.__dict__["run_id"] == "run-1"
    assert record.__dict__["model_version"] == "2026-07-01"
    assert record.__dict__["prompt_version"] == "v1"
    assert record.__dict__["skill_versions"] == "fact-extraction@v2"
    assert not hasattr(record, "prompt")
    assert not hasattr(record, "response")
