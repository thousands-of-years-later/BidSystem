"""Unit tests for the FastAPI application lifespan."""

from dataclasses import dataclass

import pytest
from fastapi import FastAPI

from bid_system.bootstrap.lifecycle import create_lifespan
from bid_system.platform.config import AppSettings


@dataclass
class FakeContainer:
    settings: AppSettings
    started: bool = False
    closed: bool = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True


def _settings() -> AppSettings:
    return AppSettings(
        APP_ENV="test",
        DATABASE_URL="postgresql+psycopg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="access",
        MINIO_SECRET_KEY="secret",
        MINIO_BUCKET="bucket",
    )


@pytest.mark.asyncio
async def test_lifespan_attaches_started_container_and_closes_it() -> None:
    settings = _settings()
    created: list[FakeContainer] = []

    def container_factory(value: AppSettings) -> FakeContainer:
        container = FakeContainer(value)
        created.append(container)
        return container

    app = FastAPI(
        lifespan=create_lifespan(
            settings_loader=lambda: settings,
            container_factory=container_factory,
        )
    )

    async with app.router.lifespan_context(app):
        assert app.state.container.started

    assert created[0].closed
