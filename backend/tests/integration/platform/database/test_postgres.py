"""PostgreSQL-specific transaction, health, and outbox behavior."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bid_system.platform.database.health import probe_database
from bid_system.platform.database.outbox import OutboxEventModel, OutboxStatus, OutboxStore


@pytest.mark.asyncio
async def test_health_probe_executes_on_postgres(db_engine: AsyncEngine) -> None:
    await probe_database(db_engine)


@pytest.mark.asyncio
async def test_outbox_row_is_written_and_claimed_in_caller_transaction(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    event = OutboxEventModel.create(
        event_type="test.created.v1",
        aggregate_type="test",
        aggregate_id="integration-1",
        aggregate_version=1,
        payload={"id": "integration-1"},
        event_metadata={"source": "integration-test"},
        occurred_at=now,
    )
    store = OutboxStore(db_session)
    store.append(event)
    await db_session.flush()

    claimed = await store.claim_batch(
        limit=1,
        now=now,
        lease_duration=timedelta(seconds=30),
    )

    assert claimed == (event,)
    assert event.status is OutboxStatus.PROCESSING
    assert event.attempt_count == 1
    result = await db_session.execute(select(func.count()).select_from(OutboxEventModel))
    assert result.scalar_one() >= 1
