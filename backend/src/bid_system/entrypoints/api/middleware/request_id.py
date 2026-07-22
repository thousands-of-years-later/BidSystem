"""Request identity and trace context middleware."""

from datetime import UTC, datetime
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bid_system.entrypoints.api.dependencies import RequestContext
from bid_system.platform.telemetry.tracing import request_span

REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"
MAX_REQUEST_ID_LENGTH = 128
REQUEST_ID_ALLOWED_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
)


def _request_id(headers: Headers) -> str:
    supplied = headers.get(REQUEST_ID_HEADER)
    if (
        supplied is not None
        and 1 <= len(supplied) <= MAX_REQUEST_ID_LENGTH
        and all(character in REQUEST_ID_ALLOWED_CHARACTERS for character in supplied)
    ):
        return supplied
    return str(uuid4())


class RequestContextMiddleware:
    """Create sanitized correlation context before any inner middleware runs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_id = _request_id(headers)
        with request_span(request_id=request_id, headers=headers) as correlation:
            client = scope.get("client")
            context = RequestContext(
                request_id=request_id,
                trace_id=correlation.trace_id,
                user_id=None,
                tenant_id=None,
                method=scope["method"],
                path=scope["path"],
                client_ip=None if client is None else client[0],
                started_at=datetime.now(UTC),
            )
            scope.setdefault("state", {})["request_context"] = context

            async def send_with_context(message: Message) -> None:
                if message["type"] == "http.response.start":
                    response_headers = MutableHeaders(scope=message)
                    response_headers[REQUEST_ID_HEADER] = request_id
                    response_headers[TRACE_ID_HEADER] = correlation.trace_id
                await send(message)

            await self.app(scope, receive, send_with_context)
