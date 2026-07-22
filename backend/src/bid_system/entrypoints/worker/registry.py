"""Explicit, typed Celery task-handler registration."""

from dataclasses import dataclass
from typing import Protocol

from celery import Celery

from bid_system.entrypoints.worker.lifecycle import WorkerRuntime
from bid_system.shared.contracts.tasks import DOCUMENT_PARSE_TASK_TYPE, DocumentParseTaskInput


class DocumentParseHandler(Protocol):
    """Future orchestration boundary for product-document parsing."""

    async def __call__(self, command: DocumentParseTaskInput) -> None: ...


@dataclass(frozen=True)
class WorkerTaskHandlers:
    """Handlers supplied by bootstrap only when their real workflows exist."""

    documents_parse: DocumentParseHandler | None = None


def register_task_handlers(
    app: Celery,
    *,
    handlers: WorkerTaskHandlers,
    runtime: WorkerRuntime,
) -> tuple[str, ...]:
    """Register only handlers backed by real application workflows."""
    registered: list[str] = []
    if handlers.documents_parse is not None:
        handler = handlers.documents_parse

        @app.task(name=DOCUMENT_PARSE_TASK_TYPE, typing=True)
        def parse_document(
            *,
            tenant_id: str,
            document_version_id: str,
        ) -> None:
            command = DocumentParseTaskInput(
                tenant_id=tenant_id,
                document_version_id=document_version_id,
            )
            runtime.run(lambda container: handler(command))

        registered.append(DOCUMENT_PARSE_TASK_TYPE)
    return tuple(registered)
