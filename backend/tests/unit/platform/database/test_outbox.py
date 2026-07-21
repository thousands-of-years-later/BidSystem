"""Unit tests for the transactional outbox state machine."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from bid_system.platform.database.outbox import (
    OutboxEventModel,
    OutboxStatus,
    OutboxStore,
    RetryPolicy,
)


def _event() -> OutboxEventModel:
    return OutboxEventModel.create(
        event_type="product_fact.published.v1",
        aggregate_type="product_fact",
        aggregate_id="fact-1",
        aggregate_version=2,
        payload={"fact_id": "fact-1"},
        event_metadata={"trace_id": "trace-1"},
    )


def test_event_has_platform_schema_and_stable_defaults() -> None:
    event = _event()

    assert OutboxEventModel.__table__.schema == "platform"
    assert event.status is OutboxStatus.PENDING
    assert event.attempt_count == 0
    assert isinstance(event.event_id, UUID)


def test_retry_returns_event_to_pending_with_bounded_backoff() -> None:
    now = datetime(2026, 7, 22, tzinfo=UTC)
    event = _event()
    event.status = OutboxStatus.PROCESSING
    event.attempt_count = 3
    claim_token = UUID("00000000-0000-0000-0000-000000000001")
    event.claim_token = claim_token
    policy = RetryPolicy(max_attempts=5, base_delay_seconds=2, max_delay_seconds=5)

    OutboxStore.apply_failure(
        event,
        claim_token=claim_token,
        now=now,
        error="temporary",
        retry_policy=policy,
    )

    assert event.status is OutboxStatus.PENDING
    assert event.available_at == now + timedelta(seconds=5)
    assert event.last_error == "temporary"
    assert event.claim_token is None


def test_retry_moves_exhausted_event_to_dead_letter_and_sanitizes_error() -> None:
    now = datetime(2026, 7, 22, tzinfo=UTC)
    event = _event()
    event.status = OutboxStatus.PROCESSING
    event.attempt_count = 5
    claim_token = UUID("00000000-0000-0000-0000-000000000001")
    event.claim_token = claim_token
    policy = RetryPolicy(max_attempts=5, base_delay_seconds=1, max_delay_seconds=10)

    OutboxStore.apply_failure(
        event,
        claim_token=claim_token,
        now=now,
        error="password=secret\nprovider failed",
        retry_policy=policy,
    )

    assert event.status is OutboxStatus.DEAD_LETTER
    assert "secret" not in (event.last_error or "")
    assert "\n" not in (event.last_error or "")


def test_stale_claim_cannot_mark_event_as_published() -> None:
    event = _event()
    event.status = OutboxStatus.PROCESSING
    event.claim_token = UUID("00000000-0000-0000-0000-000000000001")

    with pytest.raises(ValueError, match="claimed event"):
        OutboxStore.mark_published(
            event,
            claim_token=UUID("00000000-0000-0000-0000-000000000002"),
            now=datetime.now(UTC),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("event_type", " "),
        ("event_type", "x" * 201),
        ("aggregate_type", " "),
        ("aggregate_id", " "),
    ),
)
def test_event_rejects_invalid_required_identifiers(field: str, value: str) -> None:
    values = {
        "event_type": "test.created.v1",
        "aggregate_type": "test",
        "aggregate_id": "test-1",
    }
    values[field] = value

    with pytest.raises(ValueError):
        OutboxEventModel.create(
            event_type=values["event_type"],
            aggregate_type=values["aggregate_type"],
            aggregate_id=values["aggregate_id"],
            aggregate_version=1,
            payload={},
            event_metadata={},
        )


@pytest.mark.parametrize(
    ("max_attempts", "base_delay_seconds", "max_delay_seconds"),
    ((0, 1.0, 2.0), (1, 0.0, 2.0), (1, 2.0, 1.0)),
)
def test_retry_policy_rejects_invalid_bounds(
    max_attempts: int, base_delay_seconds: float, max_delay_seconds: float
) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(
            max_attempts=max_attempts,
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )
