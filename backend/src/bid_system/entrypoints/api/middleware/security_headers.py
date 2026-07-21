"""Stable API security and release headers."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bid_system import __version__

HSTS_MAX_AGE_SECONDS = 31_536_000


class SecurityHeadersMiddleware:
    """Add response hardening without imposing browser rules on domain code."""

    def __init__(self, app: ASGIApp, *, hsts_enabled: bool) -> None:
        self.app = app
        self._hsts_enabled = hsts_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-App-Version"] = __version__
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                if self._hsts_enabled:
                    headers["Strict-Transport-Security"] = (
                        f"max-age={HSTS_MAX_AGE_SECONDS}; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
