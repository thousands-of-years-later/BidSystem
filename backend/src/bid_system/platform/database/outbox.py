"""Transactional outbox persistence and deterministic retry state machine."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from bid_system.platform.config.secrets import redact_text
from bid_system.platform.database.models import OrmBase

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

PLATFORM_SCHEMA = "platform"
MAX_EVENT_TYPE_LENGTH = 200
MAX_AGGREGATE_TYPE_LENGTH = 100
MAX_AGGREGATE_ID_LENGTH = 200
MAX_ERROR_LENGTH = 2_000


class OutboxStatus(StrEnum):
    """Persisted delivery states for at-least-once publication."""

    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    DEAD_LETTER = "dead_letter"


def _outbox_status_values(enum_type: type[OutboxStatus]) -> list[str]:
    return [status.value for status in enum_type]


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry settings, expressed in seconds."""

    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.base_delay_seconds <= 0:
            raise ValueError("base_delay_seconds must be positive")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must not be below base_delay_seconds")


class OutboxEventModel(OrmBase):
    """Infrastructure-owned event envelope written with business state."""

    __tablename__ = "outbox_event"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        Index("ix_outbox_event_delivery", "status", "available_at"),
        {"schema": PLATFORM_SCHEMA},
    )

    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(MAX_EVENT_TYPE_LENGTH), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(MAX_AGGREGATE_TYPE_LENGTH), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(MAX_AGGREGATE_ID_LENGTH), nullable=False)
    aggregate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    event_metadata: Mapped[dict[str, JsonValue]] = mapped_column("metadata", JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(
            OutboxStatus,
            name="outbox_status",
            native_enum=False,
            values_callable=_outbox_status_values,
        ),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int | None,
        payload: dict[str, JsonValue],
        event_metadata: dict[str, JsonValue],
        occurred_at: datetime | None = None,
        event_id: UUID | None = None,
    ) -> "OutboxEventModel":
        """Build a pending envelope without publishing any business fact directly."""
        created_at = occurred_at or datetime.now(UTC)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        cls._validate_required_text("event_type", event_type, MAX_EVENT_TYPE_LENGTH)
        cls._validate_required_text("aggregate_type", aggregate_type, MAX_AGGREGATE_TYPE_LENGTH)
        cls._validate_required_text("aggregate_id", aggregate_id, MAX_AGGREGATE_ID_LENGTH)
        if aggregate_version is not None and aggregate_version < 0:
            raise ValueError("aggregate_version must not be negative")
        return cls(
            event_id=event_id or uuid4(),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            payload=payload,
            event_metadata=event_metadata,
            status=OutboxStatus.PENDING,
            attempt_count=0,
            available_at=created_at,
            claimed_at=None,
            claimed_until=None,
            claim_token=None,
            published_at=None,
            last_error=None,
            created_at=created_at,
        )

    @staticmethod
    def _validate_required_text(name: str, value: str, max_length: int) -> None:
        if not value.strip():
            raise ValueError(f"{name} must not be blank")
        if len(value) > max_length:
            raise ValueError(f"{name} exceeds maximum length {max_length}")


class OutboxStore:
    """Persist and lock outbox rows using a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def append(self, event: OutboxEventModel) -> None:
        self._session.add(event)

    async def claim_batch(
        self,
        *,
        limit: int,
        now: datetime,
        lease_duration: timedelta,
    ) -> tuple[OutboxEventModel, ...]:
        if limit < 1:
            raise ValueError("limit must be at least one")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        statement = (
            select(OutboxEventModel)
            .where(
                or_(
                    (OutboxEventModel.status == OutboxStatus.PENDING)
                    & (OutboxEventModel.available_at <= now),
                    (OutboxEventModel.status == OutboxStatus.PROCESSING)
                    & (OutboxEventModel.claimed_until <= now),
                )
            )
            .order_by(OutboxEventModel.available_at, OutboxEventModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = tuple((await self._session.scalars(statement)).all())
        for event in events:
            event.status = OutboxStatus.PROCESSING
            event.attempt_count += 1
            event.claimed_at = now
            event.claimed_until = now + lease_duration
            event.claim_token = uuid4()
        return events

    @staticmethod
    def mark_published(event: OutboxEventModel, *, claim_token: UUID, now: datetime) -> None:
        if event.status is not OutboxStatus.PROCESSING or event.claim_token != claim_token:
            raise ValueError("Only a claimed event can be marked as published")
        event.status = OutboxStatus.PUBLISHED
        event.published_at = now
        event.claimed_until = None
        event.claim_token = None
        event.last_error = None

    @staticmethod
    def apply_failure(
        event: OutboxEventModel,
        *,
        claim_token: UUID,
        now: datetime,
        error: str,
        retry_policy: RetryPolicy,
    ) -> None:
        if event.status is not OutboxStatus.PROCESSING or event.claim_token != claim_token:
            raise ValueError("Only a claimed event can fail publication")
        sanitized_error = redact_text(error).replace("\r", " ").replace("\n", " ")
        event.last_error = sanitized_error[:MAX_ERROR_LENGTH]
        event.claimed_at = None
        event.claimed_until = None
        event.claim_token = None
        if event.attempt_count >= retry_policy.max_attempts:
            event.status = OutboxStatus.DEAD_LETTER
            return
        delay_seconds = min(
            retry_policy.base_delay_seconds * (2 ** (event.attempt_count - 1)),
            retry_policy.max_delay_seconds,
        )
        event.status = OutboxStatus.PENDING
        event.available_at = now + timedelta(seconds=delay_seconds)
