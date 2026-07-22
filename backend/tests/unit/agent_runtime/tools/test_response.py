import pytest

from bid_system.agent_runtime.tools.response import (
    ToolError,
    ToolErrorCode,
    ToolResponse,
)


def test_tool_response_represents_success_without_error() -> None:
    response = ToolResponse.success("candidate-1")

    assert response.value == "candidate-1"
    assert response.error is None
    assert response.is_success


def test_tool_response_represents_safe_failure_without_value() -> None:
    error = ToolError(
        code=ToolErrorCode.UNAVAILABLE,
        message="document parser unavailable",
        retryable=True,
    )

    response: ToolResponse[str] = ToolResponse.failure(error)

    assert response.value is None
    assert response.error == error
    assert not response.is_success


def test_tool_error_rejects_blank_message() -> None:
    with pytest.raises(ValueError, match="message"):
        ToolError(code=ToolErrorCode.EXECUTION_FAILED, message=" ")


def test_tool_response_rejects_value_and_error_together() -> None:
    error = ToolError(code=ToolErrorCode.EXECUTION_FAILED, message="safe failure")

    with pytest.raises(ValueError, match="exactly one"):
        ToolResponse(value="candidate-1", error=error)


def test_tool_response_rejects_missing_value_and_error() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ToolResponse[str](value=None, error=None)
