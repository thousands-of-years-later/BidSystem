"""Stable error codes and public error envelopes."""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

REQUEST_ID_PATTERN = r"^[A-Za-z0-9._:-]+$"
REQUEST_ID_MAX_LENGTH = 128
RequestId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=REQUEST_ID_MAX_LENGTH,
        pattern=REQUEST_ID_PATTERN,
    ),
]


class ErrorCode(StrEnum):
    """Stable machine-readable API error codes."""

    BAD_REQUEST = "BAD_REQUEST"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    REQUEST_BODY_TOO_LARGE = "REQUEST_BODY_TOO_LARGE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    HTTP_ERROR = "HTTP_ERROR"
    APPLICATION_ERROR = "APPLICATION_ERROR"
    DOMAIN_ERROR = "DOMAIN_ERROR"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    EXTERNAL_SERVICE_UNAVAILABLE = "EXTERNAL_SERVICE_UNAVAILABLE"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


ErrorContextValue = str | int | float | bool | None


class BidSystemError(Exception):
    """Framework-neutral base for failures that may cross an application boundary."""

    code = ErrorCode.APPLICATION_ERROR
    default_public_message = "请求处理失败"

    def __init__(
        self,
        *,
        public_message: str | None = None,
        context: Mapping[str, ErrorContextValue] | None = None,
    ) -> None:
        resolved_message = self.default_public_message if public_message is None else public_message
        if not resolved_message:
            raise ValueError("public_message must not be empty")
        self.public_message = resolved_message
        # WHY: copy and freeze caller-owned data so an error remains stable while it propagates.
        self.context: Mapping[str, ErrorContextValue] = MappingProxyType(dict(context or {}))
        super().__init__(resolved_message)


class DomainError(BidSystemError):
    """Base for deterministic business-rule failures."""

    code = ErrorCode.DOMAIN_ERROR
    default_public_message = "业务规则校验失败"


class ApplicationError(BidSystemError):
    """Base for use-case orchestration failures."""

    code = ErrorCode.APPLICATION_ERROR
    default_public_message = "请求处理失败"


class ResourceNotFoundError(ApplicationError):
    """A requested application resource does not exist or is not visible."""

    code = ErrorCode.NOT_FOUND
    default_public_message = "资源不存在"


class BusinessConflictError(DomainError):
    """A request conflicts with an existing business fact."""

    code = ErrorCode.CONFLICT
    default_public_message = "请求与当前资源状态冲突"


class StateTransitionError(DomainError):
    """A requested domain state transition is not allowed."""

    code = ErrorCode.INVALID_STATE_TRANSITION
    default_public_message = "当前状态不允许执行该操作"


class AuthenticationError(ApplicationError):
    """Authentication credentials are missing or invalid."""

    code = ErrorCode.AUTHENTICATION_REQUIRED
    default_public_message = "需要身份认证"


class PermissionDeniedError(ApplicationError):
    """The authenticated principal cannot perform the use case."""

    code = ErrorCode.PERMISSION_DENIED
    default_public_message = "没有访问权限"


class ExternalServiceError(ApplicationError):
    """A required external service failed or was unavailable."""

    code = ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE
    default_public_message = "外部服务暂时不可用"


class ErrorDetail(BaseModel):
    """One safe, structured explanation for an API failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location: list[str | int]
    message: str = Field(min_length=1)
    error_type: str = Field(min_length=1)


class ErrorResponse(BaseModel):
    """Stable envelope shared by every ordinary JSON failure path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ErrorCode
    message: str = Field(min_length=1)
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: RequestId
