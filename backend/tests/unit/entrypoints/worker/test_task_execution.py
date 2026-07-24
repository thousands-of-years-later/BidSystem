"""Celery-owned task retry and terminal-failure behavior tests."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID, uuid4

from celery import Celery, Task

from bid_system.bootstrap.container import ApplicationContainer
from bid_system.entrypoints.worker.registry import WorkerTaskHandlers, register_task_handlers
from bid_system.entrypoints.worker.tasks import RetryableTaskError
from bid_system.platform.config import AppSettings
from bid_system.shared.contracts.tasks import DOCUMENT_PARSE_TASK_TYPE, DocumentParseTaskInput


def _settings() -> AppSettings:
    return AppSettings.model_validate(
        {
            "APP_ENV": "test",
            "DATABASE_URL": "postgresql+psycopg://user:password@localhost:5432/bid_system",
            "REDIS_URL": "redis://localhost:6379/0",
            "CELERY_BROKER_URL": "amqp://user:password@rabbitmq:5672//",
            "MINIO_ENDPOINT": "localhost:9000",
            "MINIO_ACCESS_KEY": "access-key",
            "MINIO_SECRET_KEY": "secret-key",
            "MINIO_BUCKET": "bid-system",
            "WORKER_MAX_RETRIES": "2",
            "WORKER_RETRY_BASE_DELAY_SECONDS": "3",
            "WORKER_RETRY_MAX_DELAY_SECONDS": "30",
        }
    )


class InlineWorkerRuntime:
    """Run async handlers inline without starting external resources."""

    def __init__(self, settings: AppSettings) -> None:
        self._container = ApplicationContainer(settings)

    def run[ResultT](
        self,
        operation: Callable[[ApplicationContainer], Awaitable[ResultT]],
    ) -> ResultT:
        return asyncio.run(_await_result(operation(self._container)))


async def _await_result[ResultT](result: Awaitable[ResultT]) -> ResultT:
    return await result


class TaskResult(Protocol):
    def failed(self) -> bool: ...

    def successful(self) -> bool: ...


class RecordingHandler:
    def __init__(self, errors: list[Exception] | None = None) -> None:
        self.calls: list[DocumentParseTaskInput] = []
        self._errors = errors or []

    async def __call__(self, command: DocumentParseTaskInput) -> None:
        self.calls.append(command)
        if self._errors:
            raise self._errors.pop(0)


def _registered_task(handler: RecordingHandler) -> tuple[Celery, Task]:
    settings = _settings()
    app = Celery("test-worker", broker="memory://")
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = False
    app.tasks.pop(DOCUMENT_PARSE_TASK_TYPE, None)
    register_task_handlers(
        app,
        handlers=WorkerTaskHandlers(documents_parse=handler),
        runtime=InlineWorkerRuntime(settings),
        worker=settings.worker,
    )
    return app, app.tasks[DOCUMENT_PARSE_TASK_TYPE]


def _apply(
    task: Task,
    *,
    document_version_id: str,
    legacy_tenant_id: str | None = None,
) -> TaskResult:
    apply = task.apply
    kwargs = {"document_version_id": document_version_id}
    if legacy_tenant_id is not None:
        kwargs["tenant_id"] = legacy_tenant_id
    result = apply(
        kwargs=kwargs,
        throw=False,
    )
    return result


def test_retries_retryable_failure_until_success() -> None:
    handler = RecordingHandler(
        errors=[
            RetryableTaskError("ocr temporarily unavailable"),
            RetryableTaskError("ocr temporarily unavailable"),
        ]
    )
    _, task = _registered_task(handler)

    result = _apply(
        task,
        document_version_id=str(uuid4()),
    )

    assert result.successful()
    assert len(handler.calls) == 3
    assert handler.calls[0].schema_version == 3
    assert task.autoretry_for == (RetryableTaskError,)
    assert task.max_retries == 2
    assert task.retry_backoff == 3
    assert task.retry_backoff_max == 30


def test_rejects_invalid_message_without_calling_handler() -> None:
    handler = RecordingHandler()
    _, task = _registered_task(handler)

    result = _apply(
        task,
        document_version_id="invalid",
    )

    assert result.failed()
    assert handler.calls == []


def test_accepts_legacy_tenant_argument_without_scoping_document() -> None:
    handler = RecordingHandler()
    _, task = _registered_task(handler)
    document_version_id = str(uuid4())

    result = _apply(
        task,
        document_version_id=document_version_id,
        legacy_tenant_id="legacy-tenant",
    )

    assert result.successful()
    assert handler.calls[0].document_version_id == UUID(document_version_id)
    assert not hasattr(handler.calls[0], "tenant_id")
