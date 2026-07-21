"""Stable public API envelope contract tests."""

import pytest
from pydantic import ValidationError

from bid_system.shared.contracts.api import (
    BatchItemResult,
    BatchOperationData,
    BatchOperationResponse,
    SuccessResponse,
)
from bid_system.shared.contracts.errors import (
    ApplicationError,
    BusinessConflictError,
    DomainError,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    ExternalServiceError,
    PermissionDeniedError,
    ResourceNotFoundError,
    StateTransitionError,
)
from bid_system.shared.contracts.pagination import PageData, PaginatedResponse, PaginationMeta

REQUEST_ID = "gateway-request_123"


def test_success_response_has_stable_envelope() -> None:
    response = SuccessResponse[dict[str, str]](
        data={"status": "ready"},
        request_id=REQUEST_ID,
    )

    assert response.model_dump(mode="json") == {
        "code": "SUCCESS",
        "message": "success",
        "data": {"status": "ready"},
        "request_id": REQUEST_ID,
    }


def test_error_response_has_stable_envelope_and_empty_details_by_default() -> None:
    response = ErrorResponse(
        code=ErrorCode.VALIDATION_ERROR,
        message="请求参数不合法",
        request_id=REQUEST_ID,
    )

    assert response.model_dump(mode="json") == {
        "code": "VALIDATION_ERROR",
        "message": "请求参数不合法",
        "details": [],
        "request_id": REQUEST_ID,
    }


def test_cross_boundary_exception_contract_is_framework_neutral_and_immutable() -> None:
    source_context = {"resource_type": "product", "resource_id": "P-001"}
    error = ResourceNotFoundError(
        public_message="产品不存在",
        context=source_context,
    )

    assert isinstance(error, ApplicationError)
    assert error.code is ErrorCode.NOT_FOUND
    assert error.public_message == "产品不存在"
    assert error.context == {"resource_type": "product", "resource_id": "P-001"}
    assert type(error.context).__name__ == "mappingproxy"
    source_context["resource_id"] = "P-002"
    assert error.context["resource_id"] == "P-001"


@pytest.mark.parametrize(
    ("error_type", "base_type", "expected_code"),
    [
        (BusinessConflictError, DomainError, ErrorCode.CONFLICT),
        (StateTransitionError, DomainError, ErrorCode.INVALID_STATE_TRANSITION),
        (PermissionDeniedError, ApplicationError, ErrorCode.PERMISSION_DENIED),
        (
            ExternalServiceError,
            ApplicationError,
            ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
        ),
    ],
)
def test_exception_categories_expose_stable_codes(
    error_type: type[ApplicationError | DomainError],
    base_type: type[ApplicationError | DomainError],
    expected_code: ErrorCode,
) -> None:
    error = error_type()

    assert isinstance(error, base_type)
    assert error.code is expected_code


def test_paginated_response_calculates_total_pages() -> None:
    response = PaginatedResponse[str](
        data=PageData(
            items=["A", "B"],
            pagination=PaginationMeta(page=2, page_size=2, total=5),
        ),
        request_id=REQUEST_ID,
    )

    assert response.data.pagination.total_pages == 3
    assert response.model_dump(mode="json")["data"] == {
        "items": ["A", "B"],
        "pagination": {"page": 2, "page_size": 2, "total": 5, "total_pages": 3},
    }


def test_batch_response_reports_consistent_summary() -> None:
    response = BatchOperationResponse[str](
        data=BatchOperationData(
            total=2,
            succeeded=1,
            failed=1,
            items=[
                BatchItemResult(index=0, success=True, data="created"),
                BatchItemResult(
                    index=1,
                    success=False,
                    error=ErrorDetail(
                        location=["items", 1],
                        message="duplicate",
                        error_type="conflict",
                    ),
                ),
            ],
        ),
        request_id=REQUEST_ID,
    )

    assert response.data.total == len(response.data.items)
    assert response.data.succeeded == 1
    assert response.data.failed == 1


@pytest.mark.parametrize(
    ("kwargs", "expected_message"),
    [
        (
            {
                "index": 0,
                "success": True,
                "data": "created",
                "error": ErrorDetail(
                    location=["items", 0], message="unexpected", error_type="invalid"
                ),
            },
            "successful batch items cannot contain an error",
        ),
        (
            {"index": 0, "success": False},
            "failed batch items require an error",
        ),
    ],
)
def test_batch_item_rejects_inconsistent_result(
    kwargs: dict[str, int | bool | str | ErrorDetail], expected_message: str
) -> None:
    with pytest.raises(ValidationError, match=expected_message):
        BatchItemResult[str](**kwargs)


def test_batch_summary_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValidationError, match="batch summary does not match item results"):
        BatchOperationData[str](
            total=1,
            succeeded=1,
            failed=0,
            items=[
                BatchItemResult(
                    index=0,
                    success=False,
                    error=ErrorDetail(
                        location=["items", 0], message="failed", error_type="invalid"
                    ),
                )
            ],
        )


def test_request_id_rejects_unsafe_or_oversized_values() -> None:
    with pytest.raises(ValidationError):
        SuccessResponse[str](data="ok", request_id="unsafe value")
    with pytest.raises(ValidationError):
        SuccessResponse[str](data="ok", request_id="x" * 129)
