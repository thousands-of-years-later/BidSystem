"""FastAPI lifespan factory for explicit resource startup and shutdown."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

from fastapi import FastAPI

from bid_system.bootstrap.container import ApplicationContainer
from bid_system.platform.config import AppSettings, load_settings
from bid_system.platform.telemetry.logging import configure_logging
from bid_system.platform.telemetry.metrics import configure_metrics, shutdown_metrics
from bid_system.platform.telemetry.tracing import configure_tracing, shutdown_tracing


class ContainerLifecycle(Protocol):
    """Container operations required by the application lifespan."""

    settings: AppSettings

    async def start(self) -> None: ...

    async def close(self) -> None: ...


SettingsLoader = Callable[[], AppSettings]
ContainerFactory = Callable[[AppSettings], ContainerLifecycle]
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _default_container_factory(settings: AppSettings) -> ContainerLifecycle:
    return ApplicationContainer(settings)


def create_lifespan(
    *,
    settings_loader: SettingsLoader = load_settings,
    container_factory: ContainerFactory = _default_container_factory,
) -> Lifespan:
    """Create a lifespan with injectable boundaries for deterministic tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = settings_loader()
        configure_logging(
            settings.logging,
            service_name=settings.tracing.service_name,
            environment=settings.environment.value,
        )
        tracer_provider = configure_tracing(
            settings.tracing,
            environment=settings.environment.value,
        )
        meter_provider = configure_metrics(
            settings.metrics,
            environment=settings.environment.value,
        )
        container = container_factory(settings)
        try:
            await container.start()
            app.state.container = container
            yield
        finally:
            try:
                await container.close()
            finally:
                shutdown_metrics(meter_provider)
                shutdown_tracing(tracer_provider)

    return lifespan
