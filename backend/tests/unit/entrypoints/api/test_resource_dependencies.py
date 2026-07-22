"""Unit tests for HTTP resource dependency accessors."""

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bid_system.bootstrap.container import ApplicationContainer
from bid_system.entrypoints.api.dependencies import (
    get_container,
    get_database_resource,
    get_minio_resource,
    get_redis_resource,
    get_settings,
)
from bid_system.platform.config import AppSettings


@dataclass
class FakeResource:
    name: str

    async def probe(self) -> None:
        return None

    async def close(self) -> None:
        return None


def _request_with_container() -> tuple[Request, ApplicationContainer]:
    settings = AppSettings(
        APP_ENV="test",
        DATABASE_URL="postgresql+psycopg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="access",
        MINIO_SECRET_KEY="secret",
        MINIO_BUCKET="bucket",
    )
    container = ApplicationContainer(settings)
    container.database = FakeResource("database")
    container.redis = FakeResource("redis")
    container.minio = FakeResource("minio")
    app = FastAPI()
    app.state.container = container
    request = Request({"type": "http", "app": app, "headers": []})
    return request, container


def test_accessors_return_resources_from_the_lifespan_container() -> None:
    request, container = _request_with_container()

    assert get_container(request) is container
    assert get_settings(request) is container.settings
    assert get_database_resource(request) is container.database
    assert get_redis_resource(request) is container.redis
    assert get_minio_resource(request) is container.minio


def test_accessor_rejects_an_uninitialized_resource() -> None:
    request, container = _request_with_container()
    container.redis = None

    with pytest.raises(RuntimeError, match="redis"):
        get_redis_resource(request)
