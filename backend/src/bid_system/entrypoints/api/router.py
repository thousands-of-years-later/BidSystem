"""Top-level HTTP router assembly."""

from fastapi import APIRouter
from fastapi.routing import APIRoute

from bid_system.entrypoints.api.routes import health, readiness, version
from bid_system.platform.config import ApiSettings


def generate_operation_id(route: APIRoute) -> str:
    """Use explicit globally unique route names as stable operation IDs."""
    return route.name


def create_root_router() -> APIRouter:
    """Create unversioned operational endpoints."""
    router = APIRouter()
    router.include_router(health.router, tags=["operations"])
    router.include_router(readiness.router, tags=["operations"])
    return router


def create_api_router(settings: ApiSettings) -> APIRouter:
    """Create the versioned public API router."""
    router = APIRouter(prefix=settings.prefix)
    router.include_router(version.router, tags=["metadata"])
    return router
