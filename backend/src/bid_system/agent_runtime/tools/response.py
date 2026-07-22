"""Safe, structured responses returned by runtime tools."""

from dataclasses import dataclass
from enum import StrEnum


class ToolErrorCode(StrEnum):
    """Stable failure categories available to runtime orchestration."""

    INVALID_INPUT = "invalid_input"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    EXECUTION_FAILED = "execution_failed"


@dataclass(frozen=True, slots=True)
class ToolError:
    """Sanitized tool failure safe to expose to runtime decision logic."""

    code: ToolErrorCode
    message: str
    retryable: bool = False

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("message must not be blank")


@dataclass(frozen=True, slots=True)
class ToolResponse[OutputT]:
    """Exactly one successful value or one structured failure."""

    value: OutputT | None
    error: ToolError | None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.error is None):
            raise ValueError("ToolResponse requires exactly one of value or error")

    @classmethod
    def success(cls, value: OutputT) -> "ToolResponse[OutputT]":
        """Build a successful response."""
        return cls(value=value, error=None)

    @classmethod
    def failure(cls, error: ToolError) -> "ToolResponse[OutputT]":
        """Build a failed response without leaking provider exceptions."""
        return cls(value=None, error=error)

    @property
    def is_success(self) -> bool:
        """Return whether this response carries a successful value."""
        return self.error is None
