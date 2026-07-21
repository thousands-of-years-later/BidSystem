"""Explicit application resource assembly and cleanup."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from bid_system.platform.config import AppSettings
from bid_system.platform.database.engine import create_database_resource
from bid_system.platform.llm.client import create_llm_client
from bid_system.platform.object_store.client import create_minio_resource
from bid_system.platform.ocr.client import create_ocr_client
from bid_system.platform.queue.redis import create_redis_resource


class LifecycleResource(Protocol):
    """Resource contract required by the bootstrap container."""

    async def probe(self) -> None: ...

    async def close(self) -> None: ...


ResourceFactory = Callable[[AppSettings], LifecycleResource]


def _database_factory(settings: AppSettings) -> LifecycleResource:
    return create_database_resource(settings.database)


def _redis_factory(settings: AppSettings) -> LifecycleResource:
    return create_redis_resource(settings.redis)


def _minio_factory(settings: AppSettings) -> LifecycleResource:
    return create_minio_resource(settings.minio)


class ExternalHttpResource:
    """Own provider-specific HTTP clients assembled at the process boundary."""

    def __init__(self, settings: AppSettings) -> None:
        self.llm_client = create_llm_client(settings.llm, settings.http_timeout_seconds)
        self.ocr_client = create_ocr_client(settings.ocr, settings.http_timeout_seconds)

    async def probe(self) -> None:
        """Provider protocols are unknown, so startup probing remains intentionally lazy."""

    async def close(self) -> None:
        """Close every enabled provider client."""
        if self.ocr_client is not None:
            await self.ocr_client.aclose()
        if self.llm_client is not None:
            await self.llm_client.aclose()


def _http_factory(settings: AppSettings) -> LifecycleResource:
    return ExternalHttpResource(settings)


@dataclass(frozen=True)
class ResourceFactories:
    """Replaceable construction boundary for deterministic lifecycle tests."""

    database: ResourceFactory = _database_factory
    redis: ResourceFactory = _redis_factory
    minio: ResourceFactory = _minio_factory
    http: ResourceFactory = _http_factory


class ContainerState(StrEnum):
    """Application container lifecycle states."""

    NEW = "new"
    STARTED = "started"
    CLOSED = "closed"


class ApplicationContainer:
    """Own all process-scoped resources and their deterministic lifecycle."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        factories: ResourceFactories | None = None,
    ) -> None:
        self.settings = settings
        self._factories = factories or ResourceFactories()
        self._resources: list[LifecycleResource] = []
        self._state = ContainerState.NEW
        self.database: LifecycleResource | None = None
        self.redis: LifecycleResource | None = None
        self.minio: LifecycleResource | None = None
        self.http: LifecycleResource | None = None

    async def start(self) -> None:
        """Build and probe critical resources, cleaning partial startup on failure."""
        if self._state is not ContainerState.NEW:
            raise RuntimeError(f"Cannot start container in state {self._state}")
        try:
            self.database = await self._create_and_probe(self._factories.database)
            self.redis = await self._create_and_probe(self._factories.redis)
            self.minio = await self._create_and_probe(self._factories.minio)
            self.http = self._create(self._factories.http)
        except BaseException:
            # WHY: startup is atomic from the process perspective; no partial pools may survive.
            await self._close_resources(suppress_errors=True)
            self._state = ContainerState.CLOSED
            raise
        self._state = ContainerState.STARTED

    def _create(self, factory: ResourceFactory) -> LifecycleResource:
        resource = factory(self.settings)
        self._resources.append(resource)
        return resource

    async def _create_and_probe(self, factory: ResourceFactory) -> LifecycleResource:
        resource = self._create(factory)
        async with asyncio.timeout(self.settings.startup.connect_timeout_seconds):
            await resource.probe()
        return resource

    async def close(self) -> None:
        """Close resources in reverse creation order; repeated closure is harmless."""
        if self._state is ContainerState.CLOSED:
            return
        await self._close_resources(suppress_errors=False)
        self._state = ContainerState.CLOSED

    async def _close_resources(self, *, suppress_errors: bool) -> None:
        errors: list[Exception] = []
        while self._resources:
            resource = self._resources.pop()
            try:
                async with asyncio.timeout(self.settings.startup.shutdown_timeout_seconds):
                    await resource.close()
            except Exception as error:
                errors.append(error)
        if errors and not suppress_errors:
            raise ExceptionGroup("One or more application resources failed to close", errors)
