"""Central HTTP error mapping and unknown-exception boundary."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bid_system.entrypoints.api.dependencies import RequestContext
from bid_system.entrypoints.api.responses import error_response
from bid_system.shared.contracts.errors import (
    ApplicationError,
    AuthenticationError,
    BidSystemError,
    BusinessConflictError,
    DomainError,
    ErrorCode,
    ErrorDetail,
    ExternalServiceError,
    PermissionDeniedError,
    ResourceNotFoundError,
    StateTransitionError,
)

ERROR_LOGGER = logging.getLogger("bid_system.api.errors")
HTTP_ERROR_CODES: dict[int, ErrorCode] = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.BAD_REQUEST,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.AUTHENTICATION_REQUIRED,
    status.HTTP_403_FORBIDDEN: ErrorCode.PERMISSION_DENIED,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_413_CONTENT_TOO_LARGE: ErrorCode.REQUEST_BODY_TOO_LARGE,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}
HTTP_ERROR_MESSAGES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "请求不合法",
    status.HTTP_401_UNAUTHORIZED: "需要身份认证",
    status.HTTP_403_FORBIDDEN: "没有访问权限",
    status.HTTP_404_NOT_FOUND: "资源不存在",
    status.HTTP_405_METHOD_NOT_ALLOWED: "请求方法不受支持",
    status.HTTP_409_CONFLICT: "请求与当前资源状态冲突",
    status.HTTP_413_CONTENT_TOO_LARGE: "请求体超过大小限制",
    status.HTTP_429_TOO_MANY_REQUESTS: "请求过于频繁",
    status.HTTP_503_SERVICE_UNAVAILABLE: "服务暂时不可用",
}
DEFAULT_HTTP_ERROR_MESSAGE = "请求失败"
SAFE_HTTP_RESPONSE_HEADERS = frozenset({"allow", "retry-after", "www-authenticate"})
VALIDATION_DETAIL_MESSAGE = "输入值不合法"
DATABASE_ERROR_MESSAGE = "数据库服务暂时不可用"


@dataclass(frozen=True)
class ExceptionHttpMapping:
    """One centralized mapping from an internal exception category to HTTP."""

    status_code: int
    code: ErrorCode


# WHY: order is significant because concrete categories must match before their base classes.
EXCEPTION_HTTP_MAPPINGS: tuple[
    tuple[type[BidSystemError], ExceptionHttpMapping], ...
] = (
    (
        ResourceNotFoundError,
        ExceptionHttpMapping(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND),
    ),
    (
        BusinessConflictError,
        ExceptionHttpMapping(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT),
    ),
    (
        StateTransitionError,
        ExceptionHttpMapping(
            status.HTTP_409_CONFLICT,
            ErrorCode.INVALID_STATE_TRANSITION,
        ),
    ),
    (
        AuthenticationError,
        ExceptionHttpMapping(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTHENTICATION_REQUIRED,
        ),
    ),
    (
        PermissionDeniedError,
        ExceptionHttpMapping(status.HTTP_403_FORBIDDEN, ErrorCode.PERMISSION_DENIED),
    ),
    (
        ExternalServiceError,
        ExceptionHttpMapping(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
        ),
    ),
    (
        ApplicationError,
        ExceptionHttpMapping(status.HTTP_400_BAD_REQUEST, ErrorCode.APPLICATION_ERROR),
    ),
    (
        DomainError,
        ExceptionHttpMapping(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.DOMAIN_ERROR,
        ),
    ),
)


def _request_id(request: Request) -> str:
    context: RequestContext = request.state.request_context
    return context.request_id


def _safe_http_headers(headers: Mapping[str, str] | None) -> dict[str, str] | None:
    if headers is None:
        return None
    safe_headers = {
        name: value for name, value in headers.items() if name.lower() in SAFE_HTTP_RESPONSE_HEADERS
    }
    return safe_headers or None


def _business_exception_mapping(exception: BidSystemError) -> ExceptionHttpMapping:
    for error_type, mapping in EXCEPTION_HTTP_MAPPINGS:
        if isinstance(exception, error_type):
            return mapping
    # All public subclasses must ultimately select one stable generic response.
    return ExceptionHttpMapping(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_SERVER_ERROR,
    )


async def validation_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Map Pydantic errors without exposing submitted values or validator context."""
    if not isinstance(exception, RequestValidationError):
        raise TypeError("validation handler received an unsupported exception")
    details = [
        ErrorDetail(
            location=list(error["loc"]),
            # WHY: custom validator messages can interpolate submitted secrets.
            message=VALIDATION_DETAIL_MESSAGE,
            error_type=error["type"],
        )
        for error in exception.errors()
    ]
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=ErrorCode.VALIDATION_ERROR,
        message="请求参数不合法",
        details=details,
        request_id=_request_id(request),
    )


async def http_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Map framework HTTP failures to the stable public envelope."""
    if not isinstance(exception, StarletteHTTPException):
        raise TypeError("HTTP handler received an unsupported exception")
    return error_response(
        status_code=exception.status_code,
        code=HTTP_ERROR_CODES.get(exception.status_code, ErrorCode.HTTP_ERROR),
        message=HTTP_ERROR_MESSAGES.get(exception.status_code, DEFAULT_HTTP_ERROR_MESSAGE),
        request_id=_request_id(request),
        headers=_safe_http_headers(exception.headers),
    )


async def business_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Map framework-neutral business failures at the HTTP boundary."""
    if not isinstance(exception, BidSystemError):
        raise TypeError("business handler received an unsupported exception")
    mapping = _business_exception_mapping(exception)
    return error_response(
        status_code=mapping.status_code,
        code=mapping.code,
        message=exception.public_message,
        request_id=_request_id(request),
    )


async def database_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Hide database diagnostics while reporting an infrastructure outage."""
    if not isinstance(exception, SQLAlchemyError):
        raise TypeError("database handler received an unsupported exception")
    context: RequestContext = request.state.request_context
    # WHY: expected constraint conflicts belong in repositories;
    # raw SQL errors are never parsed at the HTTP boundary.
    safe_error = SQLAlchemyError("Database operation failed; details redacted")
    ERROR_LOGGER.error(
        "database_request_exception",
        exc_info=(type(safe_error), safe_error, exception.__traceback__),
        extra={"request_id": context.request_id, "trace_id": context.trace_id},
    )
    return error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code=ErrorCode.DATABASE_UNAVAILABLE,
        message=DATABASE_ERROR_MESSAGE,
        request_id=context.request_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers for failures raised inside endpoint dispatch."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(BidSystemError, business_exception_handler)
    app.add_exception_handler(SQLAlchemyError, database_exception_handler)


class UnhandledExceptionMiddleware:
    """Convert unknown failures while preserving outer correlation headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def send_with_state(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_with_state)
        except Exception as error:
            context: RequestContext = scope["state"]["request_context"]
            # WHY: retain the original category and traceback while hiding arbitrary exception text.
            safe_error = RuntimeError(f"{type(error).__qualname__}: details redacted")
            ERROR_LOGGER.error(
                "unhandled_request_exception",
                exc_info=(type(safe_error), safe_error, error.__traceback__),
                extra={"request_id": context.request_id, "trace_id": context.trace_id},
            )
            # WHY: ASGI forbids starting a second response after headers have already been emitted.
            if response_started:
                raise
            response = error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="服务器内部错误",
                request_id=context.request_id,
            )
            await response(scope, receive, send)
