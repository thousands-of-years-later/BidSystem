"""Celery application factory and standalone worker command."""

import asyncio

from celery import Celery
from kombu import Exchange, Queue

from bid_system.bootstrap.container import ApplicationContainer
from bid_system.entrypoints.worker.lifecycle import WorkerRuntime, register_process_cleanup
from bid_system.entrypoints.worker.registry import WorkerTaskHandlers, register_task_handlers
from bid_system.platform.config import AppSettings, load_settings
from bid_system.platform.telemetry.logging import configure_logging
from bid_system.shared.contracts.tasks import DOCUMENT_PARSE_TASK_TYPE

CELERY_PUBLISH_MAX_RETRIES = 3
CELERY_PUBLISH_RETRY_INTERVAL_START_SECONDS = 0.2
CELERY_PUBLISH_RETRY_INTERVAL_STEP_SECONDS = 0.2
CELERY_PUBLISH_RETRY_INTERVAL_MAX_SECONDS = 1.0
DIRECT_EXCHANGE_TYPE = "direct"
PERSISTENT_DELIVERY_MODE = "persistent"
QUORUM_QUEUE_TYPE = "quorum"
TOPIC_EXCHANGE_TYPE = "topic"


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
    work_exchange = Exchange(
        f"{worker.queue_name}.tasks",
        type=TOPIC_EXCHANGE_TYPE,
        durable=True,
    )
    dead_letter_exchange_name = f"{worker.queue_name}.dlx"
    dead_letter_exchange = Exchange(
        dead_letter_exchange_name,
        type=DIRECT_EXCHANGE_TYPE,
        durable=True,
    )
    work_queue = Queue(
        worker.queue_name,
        exchange=work_exchange,
        routing_key=worker.queue_name,
        durable=True,
        queue_arguments={
            "x-queue-type": QUORUM_QUEUE_TYPE,
            "x-dead-letter-exchange": dead_letter_exchange_name,
            "x-dead-letter-routing-key": worker.dead_letter_queue_name,
            "x-delivery-limit": worker.delivery_limit,
        },
    )
    dead_letter_queue = Queue(
        worker.dead_letter_queue_name,
        exchange=dead_letter_exchange,
        routing_key=worker.dead_letter_queue_name,
        durable=True,
        queue_arguments={"x-queue-type": QUORUM_QUEUE_TYPE},
    )
    app.conf.accept_content = ("json",)
    app.conf.broker_connection_retry = True
    app.conf.broker_connection_retry_on_startup = True
    app.conf.broker_transport_options = {"confirm_publish": True}
    app.conf.enable_utc = True
    app.conf.result_backend = None
    app.conf.task_acks_late = True
    # WHY: terminal failures must be rejected to the configured DLX instead of
    # disappearing after Celery acknowledges them.
    app.conf.task_acks_on_failure_or_timeout = False
    app.conf.task_default_delivery_mode = PERSISTENT_DELIVERY_MODE
    app.conf.task_default_exchange = work_exchange.name
    app.conf.task_default_queue = worker.queue_name
    app.conf.task_default_routing_key = worker.queue_name
    app.conf.task_ignore_result = True
    app.conf.task_publish_retry = True
    app.conf.task_publish_retry_policy = {
        "max_retries": CELERY_PUBLISH_MAX_RETRIES,
        "interval_start": CELERY_PUBLISH_RETRY_INTERVAL_START_SECONDS,
        "interval_step": CELERY_PUBLISH_RETRY_INTERVAL_STEP_SECONDS,
        "interval_max": CELERY_PUBLISH_RETRY_INTERVAL_MAX_SECONDS,
    }
    app.conf.task_queues = (work_queue,)
    app.conf.task_reject_on_worker_lost = True
    app.conf.task_routes = {
        DOCUMENT_PARSE_TASK_TYPE: {
            "queue": worker.queue_name,
            "routing_key": worker.queue_name,
        }
    }
    app.conf.task_serializer = "json"
    app.conf.task_soft_time_limit = worker.soft_time_limit_seconds
    app.conf.task_time_limit = worker.hard_time_limit_seconds
    app.conf.timezone = "UTC"
    app.conf.worker_cancel_long_running_tasks_on_connection_loss = True
    app.conf.worker_concurrency = worker.concurrency
    app.conf.worker_detect_quorum_queues = True
    # WHY: RabbitMQ 4 rejects Celery's transient non-exclusive pidbox queues.
    # Task delivery does not depend on remote-control broadcasts.
    app.conf.worker_enable_remote_control = False
    app.conf.worker_dead_letter_queue = dead_letter_queue
    app.conf.worker_hijack_root_logger = False
    app.conf.worker_prefetch_multiplier = worker.prefetch_multiplier
    runtime = WorkerRuntime(resolved_settings)
    register_process_cleanup(runtime)
    register_task_handlers(
        app,
        handlers=handlers or WorkerTaskHandlers(),
        runtime=runtime,
        worker=worker,
    )
    return app


celery_app = create_celery_app()


def _declare_dead_letter_queue(app: Celery) -> None:
    """Declare the DLQ without adding it to the Worker's consumed queues."""
    with app.connection_for_write() as connection:
        app.conf.worker_dead_letter_queue.declare(channel=connection.default_channel)


def main() -> None:
    """Run the independently deployable Celery worker process."""
    _declare_dead_letter_queue(celery_app)
    celery_app.worker_main(
        argv=(
            "worker",
            "--loglevel=INFO",
            "--hostname=worker@%h",
            f"--queues={celery_app.conf.task_default_queue}",
            "--without-gossip",
            "--without-mingle",
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
    _declare_dead_letter_queue(celery_app)
    asyncio.run(_probe_dependencies(load_settings()))
