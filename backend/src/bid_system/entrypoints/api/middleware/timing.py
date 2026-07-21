"""Request duration middleware."""

from time import perf_counter_ns

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

NANOSECONDS_PER_MILLISECOND = 1_000_000


class TimingMiddleware:
    """Measure server processing time with a monotonic clock."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started_ns = perf_counter_ns()

        async def send_with_timing(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration_ms = (perf_counter_ns() - started_ns) / NANOSECONDS_PER_MILLISECOND
                MutableHeaders(scope=message)["Server-Timing"] = f"app;dur={duration_ms:.3f}"
                scope["state"]["duration_ms"] = duration_ms
            await send(message)

        await self.app(scope, receive, send_with_timing)
