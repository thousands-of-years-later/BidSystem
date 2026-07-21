"""Stable success and batch API contracts with serialization primitives."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PlainSerializer,
    model_validator,
)

from bid_system.shared.contracts.errors import ErrorDetail
from bid_system.shared.contracts.errors import RequestId as RequestId

SUCCESS_MESSAGE = "success"


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def _serialize_money(value: Decimal) -> str:
    return format(value, "f")


UtcDateTime = Annotated[datetime, AfterValidator(_normalize_utc)]
MoneyAmount = Annotated[
    Decimal,
    Field(allow_inf_nan=False),
    PlainSerializer(_serialize_money, return_type=str, when_used="json"),
]


class ApiContractModel(BaseModel):
    """Base configuration for immutable public contract models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SuccessResponse[ResponseDataT](ApiContractModel):
    """Stable success envelope for ordinary JSON APIs."""

    code: Literal["SUCCESS"] = "SUCCESS"
    message: str = Field(default=SUCCESS_MESSAGE, min_length=1)
    data: ResponseDataT
    request_id: RequestId


class BatchItemResult[ResponseDataT](ApiContractModel):
    """Observable result for one position in a batch request."""

    index: NonNegativeInt
    success: bool
    data: ResponseDataT | None = None
    error: ErrorDetail | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> Self:
        if self.success and self.error is not None:
            raise ValueError("successful batch items cannot contain an error")
        if not self.success and self.error is None:
            raise ValueError("failed batch items require an error")
        if not self.success and self.data is not None:
            raise ValueError("failed batch items cannot contain data")
        return self


class BatchOperationData[ResponseDataT](ApiContractModel):
    """Summary and ordered item results for a batch operation."""

    total: NonNegativeInt
    succeeded: NonNegativeInt
    failed: NonNegativeInt
    items: list[BatchItemResult[ResponseDataT]]

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        succeeded = sum(item.success for item in self.items)
        failed = len(self.items) - succeeded
        expected_indexes: Sequence[int] = range(len(self.items))
        actual_indexes = [item.index for item in self.items]
        if (
            self.total != len(self.items)
            or self.succeeded != succeeded
            or self.failed != failed
            or actual_indexes != list(expected_indexes)
        ):
            raise ValueError("batch summary does not match item results")
        return self


class BatchOperationResponse[ResponseDataT](SuccessResponse[BatchOperationData[ResponseDataT]]):
    """Stable success envelope for batch operations."""
