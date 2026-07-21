"""One structured completion log per HTTP request."""

import logging
from time import perf_counter_ns

from starlette import status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bid_system.entrypoints.api.dependencies import RequestContext
from bid_system.entrypoints.api.middleware.timing import NANOSECONDS_PER_MILLISECOND

ACCESS_LOGGER = logging.getLogger("bid_system.access")


class AccessLogMiddleware:
    """Log sanitized request metadata after completion or failure."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started_ns = perf_counter_ns()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            duration_ms = (perf_counter_ns() - started_ns) / NANOSECONDS_PER_MILLISECOND
            context: RequestContext = scope["state"]["request_context"]
            ACCESS_LOGGER.info(
                "request_completed",
                extra={
                    "request_id": context.request_id,
                    "trace_id": context.trace_id,
                    "user_id": context.user_id,
                    "tenant_id": context.tenant_id,
                    "method": context.method,
                    "path": context.path,
                    "client_ip": context.client_ip,
                    "started_at": context.started_at.isoformat(),
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
