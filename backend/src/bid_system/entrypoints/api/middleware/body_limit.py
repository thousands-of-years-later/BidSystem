"""Request body size enforcement for declared and streamed payloads."""

from starlette import status
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bid_system.entrypoints.api.dependencies import RequestContext
from bid_system.entrypoints.api.responses import error_response
from bid_system.shared.contracts.errors import ErrorCode


class RequestBodyTooLargeError(Exception):
    """Raised when streamed body bytes exceed the configured boundary."""


class RequestBodyLimitMiddleware:
    """Reject oversized payloads before unbounded bytes reach endpoint code."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        document_upload_path_prefix: str,
        document_upload_max_body_bytes: int,
    ) -> None:
        self.app = app
        self._max_body_bytes = max_body_bytes
        self._document_upload_path_prefix = document_upload_path_prefix
        self._document_upload_max_body_bytes = document_upload_max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_body_bytes = self._limit_for_scope(scope)
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None and self._declared_size_exceeds_limit(
            content_length,
            max_body_bytes,
        ):
            await self._send_rejection(scope, receive, send)
            return
        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > max_body_bytes:
                    raise RequestBodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLargeError:
            await self._send_rejection(scope, receive, send)

    def _limit_for_scope(self, scope: Scope) -> int:
        path = scope.get("path", "")
        method = scope.get("method", "")
        if method == "POST" and path.startswith(self._document_upload_path_prefix):
            return self._document_upload_max_body_bytes
        return self._max_body_bytes

    @staticmethod
    def _declared_size_exceeds_limit(content_length: str, max_body_bytes: int) -> bool:
        try:
            return int(content_length) > max_body_bytes
        except ValueError:
            return True

    async def _send_rejection(self, scope: Scope, receive: Receive, send: Send) -> None:
        context: RequestContext = scope["state"]["request_context"]
        response = error_response(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code=ErrorCode.REQUEST_BODY_TOO_LARGE,
            message="请求体超过大小限制",
            request_id=context.request_id,
        )
        await response(scope, receive, send)
