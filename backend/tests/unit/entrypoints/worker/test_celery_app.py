"""Celery application configuration tests."""

from kombu import Queue

from bid_system.entrypoints.worker.app import create_celery_app
from bid_system.platform.config import AppSettings


def _settings(**overrides: str) -> AppSettings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+psycopg://user:password@localhost:5432/bid_system",
        "REDIS_URL": "redis://localhost:6379/0",
        "CELERY_BROKER_URL": "amqp://user:password@rabbitmq:5672//",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "access-key",
        "MINIO_SECRET_KEY": "secret-key",
        "MINIO_BUCKET": "bid-system",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def _queue(app_queues: tuple[Queue, ...], name: str) -> Queue:
    return next(queue for queue in app_queues if queue.name == name)


def test_configures_bounded_at_least_once_delivery_with_dead_letter_queue() -> None:
    settings = _settings(
        WORKER_QUEUE_NAME="documents",
        WORKER_DEAD_LETTER_QUEUE_NAME="documents.dead",
        WORKER_DELIVERY_LIMIT="5",
    )

    app = create_celery_app(settings=settings)
    queues = tuple(app.conf.task_queues)
    work_queue = _queue(queues, "documents")
    dead_letter_queue = app.conf.worker_dead_letter_queue

    assert app.conf.task_acks_late is True
    assert app.conf.task_acks_on_failure_or_timeout is False
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.task_publish_retry is True
    assert app.conf.broker_transport_options == {"confirm_publish": True}
    assert app.conf.worker_enable_remote_control is False
    assert work_queue.durable is True
    assert work_queue.queue_arguments == {
        "x-queue-type": "quorum",
        "x-dead-letter-exchange": "documents.dlx",
        "x-dead-letter-routing-key": "documents.dead",
        "x-delivery-limit": 5,
    }
    assert dead_letter_queue.durable is True
    assert dead_letter_queue.queue_arguments == {"x-queue-type": "quorum"}
    assert work_queue.exchange.name == "documents.tasks"
    assert work_queue.exchange.type == "topic"
    assert dead_letter_queue.exchange.name == "documents.dlx"


def test_does_not_apply_redis_visibility_timeout_to_rabbitmq() -> None:
    settings = AppSettings.model_validate(
        {
            "APP_ENV": "test",
            "DATABASE_URL": "postgresql+psycopg://user:password@localhost:5432/bid_system",
            "REDIS_URL": "redis://localhost:6379/0",
            "CELERY_BROKER_URL": "amqp://user:password@rabbitmq:5672//",
            "MINIO_ENDPOINT": "localhost:9000",
            "MINIO_ACCESS_KEY": "access-key",
            "MINIO_SECRET_KEY": "secret-key",
            "MINIO_BUCKET": "bid-system",
        }
    )

    app = create_celery_app(settings=settings)

    assert settings.celery.broker_url.get_secret_value().startswith("amqp://")
    assert "visibility_timeout" not in app.conf.broker_transport_options
