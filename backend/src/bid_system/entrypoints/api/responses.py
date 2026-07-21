"""HTTP-specific DTOs and mappings to stable shared API contracts.

File downloads, server-sent events, and other streaming responses bypass the
ordinary JSON envelope because wrapping would break their transport semantics.
"""

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel
from starlette.responses import JSONResponse

from bid_system.shared.contracts.api import SUCCESS_MESSAGE, SuccessResponse
from bid_system.shared.contracts.errors import ErrorCode, ErrorDetail, ErrorResponse


class LivenessStatus(StrEnum):
    """Process liveness states."""

    ALIVE = "alive"


class HealthResponse(BaseModel):
    """Process liveness response."""

    status: LivenessStatus


class ReadinessStatus(StrEnum):
    """Aggregate readiness states."""

    READY = "ready"
    NOT_READY = "not_ready"


class CheckStatus(StrEnum):
    """Individual dependency probe states."""

    UP = "up"
    DOWN = "down"


class ReadinessResponse(BaseModel):
    """Sanitized readiness result for critical infrastructure."""

    status: ReadinessStatus
    checks: dict[str, CheckStatus]


class VersionResponse(BaseModel):
    """Application version response."""

    version: str


def success_response[ResponseDataT](
    *,
    data: ResponseDataT,
    request_id: str,
    message: str = SUCCESS_MESSAGE,
) -> SuccessResponse[ResponseDataT]:
    """Map an application DTO to the ordinary JSON success envelope."""
    return SuccessResponse(data=data, message=message, request_id=request_id)


def error_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    request_id: str,
    details: list[ErrorDetail] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Map a safe failure description to an HTTP JSON response."""
    error = ErrorResponse(
        code=code,
        message=message,
        details=[] if details is None else details,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(mode="json"),
        headers=headers,
    )
