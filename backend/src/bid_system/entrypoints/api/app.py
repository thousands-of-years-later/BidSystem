"""FastAPI application factory."""

from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import HTMLResponse

from bid_system import __version__
from bid_system.bootstrap.lifecycle import ContainerFactory, create_lifespan
from bid_system.entrypoints.api.exception_handlers import (
    UnhandledExceptionMiddleware,
    register_exception_handlers,
)
from bid_system.entrypoints.api.middleware.access_log import AccessLogMiddleware
from bid_system.entrypoints.api.middleware.body_limit import RequestBodyLimitMiddleware
from bid_system.entrypoints.api.middleware.request_id import RequestContextMiddleware
from bid_system.entrypoints.api.middleware.security_headers import SecurityHeadersMiddleware
from bid_system.entrypoints.api.middleware.timing import TimingMiddleware
from bid_system.entrypoints.api.router import (
    create_api_router,
    create_root_router,
    generate_operation_id,
)
from bid_system.platform.config import AppSettings, load_settings

API_DOCS_URL = "/docs"
OPENAPI_SCHEMA_URL = "/openapi.json"


def create_app(
    *,
    settings: AppSettings | None = None,
    container_factory: ContainerFactory | None = None,
) -> FastAPI:
    """Build an application without opening external connections until lifespan starts."""
    resolved_settings = settings or load_settings()
    lifespan = (
        create_lifespan(settings_loader=lambda: resolved_settings)
        if container_factory is None
        else create_lifespan(
            settings_loader=lambda: resolved_settings,
            container_factory=container_factory,
        )
    )
    docs_enabled = resolved_settings.api.docs_enabled
    app = FastAPI(
        title=resolved_settings.api.title,
        description=resolved_settings.api.description,
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=OPENAPI_SCHEMA_URL if docs_enabled else None,
        generate_unique_id_function=generate_operation_id,
        lifespan=lifespan,
    )

    if docs_enabled:
        _register_api_reference(app)
    app.include_router(create_root_router())
    app.include_router(create_api_router(resolved_settings.api))
    register_exception_handlers(app)
    _register_middlewares(app, resolved_settings)
    return app


def _register_api_reference(app: FastAPI) -> None:
    """Expose Scalar as the only interactive API reference."""

    async def scalar_api_reference() -> HTMLResponse:
        return get_scalar_api_reference(
            openapi_url=OPENAPI_SCHEMA_URL,
            title=f"{app.title} - API Reference",
        )

    # WHY: The documentation renderer is infrastructure, not part of the public API contract.
    app.add_api_route(
        API_DOCS_URL,
        scalar_api_reference,
        include_in_schema=False,
        methods=["GET"],
    )


def _register_middlewares(app: FastAPI, settings: AppSettings) -> None:
    """Register from innermost to outermost; Starlette prepends each middleware."""
    api = settings.api
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=api.max_request_body_bytes)
    app.add_middleware(GZipMiddleware, minimum_size=api.gzip_minimum_size_bytes)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(api.trusted_hosts))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(api.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=api.hsts_enabled)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(UnhandledExceptionMiddleware)
    app.add_middleware(RequestContextMiddleware)
