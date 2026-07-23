"""Top-level HTTP router assembly."""

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute

from bid_system.entrypoints.api.dependencies import get_current_principal
from bid_system.entrypoints.api.routes import auth, health, readiness, version
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
    router.include_router(auth.router, tags=["authentication"])
    # WHY: business routers belong under this authenticated parent so a new route cannot
    # accidentally become anonymous merely because its author omitted a local dependency.
    authenticated = APIRouter(dependencies=[Depends(get_current_principal)])
    authenticated.include_router(version.router, tags=["metadata"])
    router.include_router(authenticated)
    return router
