"""Celery application configuration tests."""

from bid_system.entrypoints.worker.app import create_celery_app
from bid_system.platform.config import AppSettings


def test_does_not_apply_redis_transport_options_to_rabbitmq() -> None:
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
