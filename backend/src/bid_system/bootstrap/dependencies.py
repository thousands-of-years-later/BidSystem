"""FastAPI dependency accessors for resources assembled by lifespan."""

from fastapi import Request

from bid_system.bootstrap.container import ApplicationContainer, LifecycleResource
from bid_system.platform.config import AppSettings


def get_container(request: Request) -> ApplicationContainer:
    """Return the application-scoped dependency container."""
    container: ApplicationContainer = request.app.state.container
    return container


def get_settings(request: Request) -> AppSettings:
    """Return validated settings through the application container."""
    return get_container(request).settings


def _required_resource(resource: LifecycleResource | None, name: str) -> LifecycleResource:
    if resource is None:
        raise RuntimeError(f"Application resource is not initialized: {name}")
    return resource


def get_database_resource(request: Request) -> LifecycleResource:
    """Return the initialized database resource."""
    return _required_resource(get_container(request).database, "database")


def get_redis_resource(request: Request) -> LifecycleResource:
    """Return the initialized Redis resource."""
    return _required_resource(get_container(request).redis, "redis")


def get_minio_resource(request: Request) -> LifecycleResource:
    """Return the initialized MinIO resource."""
    return _required_resource(get_container(request).minio, "minio")
