"""Request identity and trace context middleware."""

import re
from datetime import UTC, datetime
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bid_system.entrypoints.api.dependencies import RequestContext

REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
TRACEPARENT_PATTERN = re.compile(
    r"^[0-9a-f]{2}-(?P<trace_id>[0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$"
)


def _request_id(headers: Headers) -> str:
    supplied = headers.get(REQUEST_ID_HEADER)
    if supplied is not None and REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return str(uuid4())


def _trace_id(headers: Headers) -> str:
    supplied = headers.get("traceparent")
    match = None if supplied is None else TRACEPARENT_PATTERN.fullmatch(supplied.lower())
    if match is not None and match.group("trace_id") != "0" * 32:
        return match.group("trace_id")
    return uuid4().hex


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
        trace_id = _trace_id(headers)
        client = scope.get("client")
        context = RequestContext(
            request_id=request_id,
            trace_id=trace_id,
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
                response_headers[TRACE_ID_HEADER] = trace_id
            await send(message)

        await self.app(scope, receive, send_with_context)
