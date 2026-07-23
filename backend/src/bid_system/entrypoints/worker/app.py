"""Celery application factory and standalone worker command."""

import asyncio

from celery import Celery

from bid_system.bootstrap.container import ApplicationContainer
from bid_system.entrypoints.worker.lifecycle import WorkerRuntime, register_process_cleanup
from bid_system.entrypoints.worker.registry import WorkerTaskHandlers, register_task_handlers
from bid_system.platform.config import AppSettings, load_settings
from bid_system.platform.telemetry.logging import configure_logging
from bid_system.shared.contracts.tasks import DOCUMENT_PARSE_TASK_TYPE


def create_celery_app(
    *,
    settings: AppSettings | None = None,
    handlers: WorkerTaskHandlers | None = None,
) -> Celery:
    """Build a Celery app without opening database, Redis, or HTTP connections."""
    resolved_settings = settings or load_settings()
    worker = resolved_settings.worker
    configure_logging(
        resolved_settings.logging,
        service_name=resolved_settings.tracing.service_name,
        environment=resolved_settings.environment.value,
    )
    app = Celery("bid_system", broker=resolved_settings.celery.broker_url.get_secret_value())
    app.conf.accept_content = ("json",)
    app.conf.broker_connection_retry = True
    app.conf.broker_connection_retry_on_startup = True
    app.conf.enable_utc = True
    app.conf.result_backend = None
    app.conf.task_acks_late = True
    app.conf.task_acks_on_failure_or_timeout = True
    app.conf.task_default_queue = worker.queue_name
    app.conf.task_ignore_result = True
    app.conf.task_routes = {DOCUMENT_PARSE_TASK_TYPE: {"queue": worker.queue_name}}
    app.conf.task_serializer = "json"
    app.conf.task_soft_time_limit = worker.soft_time_limit_seconds
    app.conf.task_time_limit = worker.hard_time_limit_seconds
    app.conf.timezone = "UTC"
    app.conf.worker_cancel_long_running_tasks_on_connection_loss = True
    app.conf.worker_concurrency = worker.concurrency
    app.conf.worker_hijack_root_logger = False
    app.conf.worker_prefetch_multiplier = worker.prefetch_multiplier
    runtime = WorkerRuntime(resolved_settings)
    register_process_cleanup(runtime)
    register_task_handlers(
        app,
        handlers=handlers or WorkerTaskHandlers(),
        runtime=runtime,
    )
    return app


celery_app = create_celery_app()


def main() -> None:
    """Run the independently deployable Celery worker process."""
    celery_app.worker_main(
        argv=(
            "worker",
            "--loglevel=INFO",
            "--hostname=worker@%h",
        )
    )


async def _probe_dependencies(settings: AppSettings) -> None:
    container = ApplicationContainer(settings)
    try:
        await container.start()
    finally:
        await container.close()


def healthcheck() -> None:
    """Fail unless the Worker process dependencies can start and stop cleanly."""
    asyncio.run(_probe_dependencies(load_settings()))
