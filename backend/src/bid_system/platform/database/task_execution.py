"""Persistent idempotency and delivery state for asynchronous task execution."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Integer, String, Text, Uuid, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from bid_system.platform.config.secrets import redact_text
from bid_system.platform.database.models import OrmBase

PLATFORM_SCHEMA = "platform"
MAX_TASK_TYPE_LENGTH = 200
MAX_TASK_ERROR_LENGTH = 2_000


class TaskExecutionStatus(StrEnum):
    """Authoritative technical execution states."""

    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"


class TaskClaimDisposition(StrEnum):
    """Observable outcomes when an at-least-once delivery is claimed."""

    CLAIMED = "claimed"
    BUSY = "busy"
    NOT_READY = "not_ready"
    ALREADY_SUCCEEDED = "already_succeeded"
    DEAD_LETTERED = "dead_lettered"


def _task_status_values(enum_type: type[TaskExecutionStatus]) -> list[str]:
    return [status.value for status in enum_type]


@dataclass(frozen=True)
class TaskRetryPolicy:
    """Bounded retry policy expressed in seconds."""

    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.base_delay_seconds < 1:
            raise ValueError("base_delay_seconds must be at least one")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must not be below base_delay_seconds")


@dataclass(frozen=True)
class TaskClaimResult:
    """Claim result without leaking an ORM entity across the infrastructure boundary."""

    disposition: TaskClaimDisposition
    claim_token: UUID | None
    attempt_count: int


class TaskExecutionModel(OrmBase):
    """Platform-owned execution ledger; business progress remains module-owned."""

    __tablename__ = "task_execution"
    __table_args__ = (
        CheckConstraint("attempt_count >= 1", name="attempt_count_positive"),
        Index("ix_task_execution_delivery", "status", "available_at"),
        {"schema": PLATFORM_SCHEMA},
    )

    task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(MAX_TASK_TYPE_LENGTH), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[TaskExecutionStatus] = mapped_column(
        Enum(
            TaskExecutionStatus,
            name="task_execution_status",
            native_enum=False,
            values_callable=_task_status_values,
        ),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskExecutionStore:
    """Serialize claims and transitions inside a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        *,
        task_id: UUID,
        task_type: str,
        tenant_id: UUID,
        now: datetime,
        lease_duration: timedelta,
    ) -> TaskClaimResult:
        self._validate_claim_input(task_type=task_type, now=now, lease_duration=lease_duration)
        claim_token = uuid4()
        inserted_task_id = await self._session.scalar(
            insert(TaskExecutionModel)
            .values(
                task_id=task_id,
                task_type=task_type,
                tenant_id=tenant_id,
                status=TaskExecutionStatus.RUNNING,
                attempt_count=1,
                claim_token=claim_token,
                claimed_at=now,
                claimed_until=now + lease_duration,
                available_at=now,
                completed_at=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=[TaskExecutionModel.task_id])
            .returning(TaskExecutionModel.task_id)
        )
        if inserted_task_id is not None:
            return TaskClaimResult(TaskClaimDisposition.CLAIMED, claim_token, 1)

        execution = await self._get_for_update(task_id)
        self._validate_delivery_identity(execution, task_type=task_type, tenant_id=tenant_id)
        if execution.status is TaskExecutionStatus.SUCCEEDED:
            return TaskClaimResult(
                TaskClaimDisposition.ALREADY_SUCCEEDED,
                None,
                execution.attempt_count,
            )
        if execution.status is TaskExecutionStatus.DEAD_LETTER:
            return TaskClaimResult(
                TaskClaimDisposition.DEAD_LETTERED,
                None,
                execution.attempt_count,
            )
        if execution.status is TaskExecutionStatus.RETRY_SCHEDULED and execution.available_at > now:
            return TaskClaimResult(
                TaskClaimDisposition.NOT_READY,
                None,
                execution.attempt_count,
            )
        if (
            execution.status is TaskExecutionStatus.RUNNING
            and execution.claimed_until is not None
            and execution.claimed_until > now
        ):
            return TaskClaimResult(TaskClaimDisposition.BUSY, None, execution.attempt_count)

        execution.status = TaskExecutionStatus.RUNNING
        execution.attempt_count += 1
        execution.claim_token = claim_token
        execution.claimed_at = now
        execution.claimed_until = now + lease_duration
        execution.updated_at = now
        return TaskClaimResult(
            TaskClaimDisposition.CLAIMED,
            claim_token,
            execution.attempt_count,
        )

    async def mark_succeeded(
        self,
        *,
        task_id: UUID,
        claim_token: UUID,
        now: datetime,
    ) -> None:
        execution = await self._get_for_update(task_id)
        self._require_active_claim(execution, claim_token)
        execution.status = TaskExecutionStatus.SUCCEEDED
        execution.claim_token = None
        execution.claimed_until = None
        execution.completed_at = now
        execution.last_error = None
        execution.updated_at = now

    async def apply_failure(
        self,
        *,
        task_id: UUID,
        claim_token: UUID,
        now: datetime,
        error: str,
        retry_policy: TaskRetryPolicy,
    ) -> TaskExecutionStatus:
        execution = await self._get_for_update(task_id)
        self._require_active_claim(execution, claim_token)
        execution.claim_token = None
        execution.claimed_at = None
        execution.claimed_until = None
        execution.updated_at = now
        sanitized_error = redact_text(error).replace("\r", " ").replace("\n", " ")
        execution.last_error = sanitized_error[:MAX_TASK_ERROR_LENGTH]
        if execution.attempt_count >= retry_policy.max_attempts:
            execution.status = TaskExecutionStatus.DEAD_LETTER
            execution.completed_at = now
            return execution.status
        delay_seconds = min(
            retry_policy.base_delay_seconds * (2 ** (execution.attempt_count - 1)),
            retry_policy.max_delay_seconds,
        )
        execution.status = TaskExecutionStatus.RETRY_SCHEDULED
        execution.available_at = now + timedelta(seconds=delay_seconds)
        return execution.status

    async def _get_for_update(self, task_id: UUID) -> TaskExecutionModel:
        execution = await self._session.scalar(
            select(TaskExecutionModel)
            .where(TaskExecutionModel.task_id == task_id)
            .with_for_update()
        )
        if execution is None:
            raise LookupError("Task execution does not exist")
        return execution

    @staticmethod
    def _validate_claim_input(
        *,
        task_type: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> None:
        if not task_type.strip() or len(task_type) > MAX_TASK_TYPE_LENGTH:
            raise ValueError("task_type is invalid")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must include a timezone")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")

    @staticmethod
    def _validate_delivery_identity(
        execution: TaskExecutionModel,
        *,
        task_type: str,
        tenant_id: UUID,
    ) -> None:
        if execution.task_type != task_type or execution.tenant_id != tenant_id:
            raise ValueError("task_id was reused with different delivery identity")

    @staticmethod
    def _require_active_claim(execution: TaskExecutionModel, claim_token: UUID) -> None:
        if execution.status is not TaskExecutionStatus.RUNNING:
            raise ValueError("Task execution is not running")
        if execution.claim_token != claim_token:
            raise ValueError("Task claim token is stale")
