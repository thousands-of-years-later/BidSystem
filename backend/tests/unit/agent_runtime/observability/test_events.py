from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from bid_system.agent_runtime.context.run import (
    RunContext,
    RunIdentity,
    RuntimeVersions,
    SkillVersion,
)
from bid_system.agent_runtime.observability.events import RuntimeEvent, RuntimeEventType


def _context() -> RunContext:
    return RunContext(
        identity=RunIdentity(run_id="run-1", request_id="request-1", trace_id="1" * 32),
        versions=RuntimeVersions(
            model_name="extractor",
            model_version="2026-07-01",
            prompt_name="product-fact-extract",
            prompt_version="v1",
            skills=(SkillVersion(name="fact-extraction", version="v2"),),
        ),
    )


def test_runtime_event_carries_identity_and_version_snapshot() -> None:
    event = RuntimeEvent(
        event_type=RuntimeEventType.TOOL_SUCCEEDED,
        occurred_at=datetime(2026, 7, 22, tzinfo=UTC),
        context=_context(),
        tool_name="extract_document",
        attempt=1,
        duration_ms=12.5,
    )

    assert event.context.identity.run_id == "run-1"
    assert event.context.versions.model_version == "2026-07-01"
    assert event.context.versions.prompt_version == "v1"
    assert event.context.versions.skills[0].version == "v2"
    assert event.error_code is None


def test_runtime_event_supports_only_bounded_metadata() -> None:
    assert "payload" not in RuntimeEvent.__dataclass_fields__
    assert "prompt" not in RuntimeEvent.__dataclass_fields__
    assert "response" not in RuntimeEvent.__dataclass_fields__


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: RuntimeEvent(
                event_type=RuntimeEventType.TOOL_FAILED,
                occurred_at=datetime(2026, 7, 22, tzinfo=UTC),
                context=_context(),
                tool_name=" ",
                attempt=1,
                duration_ms=1.0,
            ),
            "tool_name",
        ),
        (
            lambda: RuntimeEvent(
                event_type=RuntimeEventType.TOOL_FAILED,
                occurred_at=datetime(2026, 7, 22, tzinfo=UTC),
                context=_context(),
                tool_name="extract_document",
                attempt=0,
                duration_ms=1.0,
            ),
            "attempt",
        ),
        (
            lambda: RuntimeEvent(
                event_type=RuntimeEventType.TOOL_FAILED,
                occurred_at=datetime(2026, 7, 22, tzinfo=UTC),
                context=_context(),
                tool_name="extract_document",
                attempt=1,
                duration_ms=-0.1,
            ),
            "duration_ms",
        ),
        (
            lambda: RuntimeEvent(
                event_type=RuntimeEventType.TOOL_FAILED,
                occurred_at=datetime(2026, 7, 22, tzinfo=UTC),
                context=_context(),
                tool_name="extract_document",
                attempt=1,
                duration_ms=1.0,
                retry_delay_seconds=-0.1,
            ),
            "retry_delay_seconds",
        ),
    ],
)
def test_runtime_event_rejects_invalid_metadata(
    factory: Callable[[], RuntimeEvent],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()
