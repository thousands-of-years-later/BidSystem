"""Unit tests for resource assembly and cleanup."""

from dataclasses import dataclass, field

import pytest

from bid_system.bootstrap.container import ApplicationContainer, ResourceFactories
from bid_system.platform.config import AppSettings


@dataclass
class FakeResource:
    name: str
    events: list[str]
    fail_probe: bool = False
    client: str = field(init=False)

    def __post_init__(self) -> None:
        self.client = self.name

    async def probe(self) -> None:
        self.events.append(f"probe:{self.name}")
        if self.fail_probe:
            raise TimeoutError(self.name)

    async def close(self) -> None:
        self.events.append(f"close:{self.name}")


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
async def test_container_starts_and_closes_resources_in_reverse_order() -> None:
    events: list[str] = []
    resources = {
        name: FakeResource(name, events) for name in ("database", "redis", "minio", "http")
    }
    factories = ResourceFactories(
        database=lambda settings: resources["database"],
        redis=lambda settings: resources["redis"],
        minio=lambda settings: resources["minio"],
        http=lambda settings: resources["http"],
    )
    container = ApplicationContainer(_settings(), factories=factories)

    await container.start()
    await container.close()

    assert events == [
        "probe:database",
        "probe:redis",
        "probe:minio",
        "close:http",
        "close:minio",
        "close:redis",
        "close:database",
    ]


@pytest.mark.asyncio
async def test_partial_start_failure_cleans_up_created_resources() -> None:
    events: list[str] = []
    database = FakeResource("database", events)
    redis = FakeResource("redis", events, fail_probe=True)
    factories = ResourceFactories(
        database=lambda settings: database,
        redis=lambda settings: redis,
        minio=lambda settings: FakeResource("minio", events),
        http=lambda settings: FakeResource("http", events),
    )
    container = ApplicationContainer(_settings(), factories=factories)

    with pytest.raises(TimeoutError, match="redis"):
        await container.start()

    assert events == [
        "probe:database",
        "probe:redis",
        "close:redis",
        "close:database",
    ]
