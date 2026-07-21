"""Stable contracts shared across business modules and external API adapters."""

from bid_system.shared.contracts.api import (
    ApiContractModel,
    BatchItemResult,
    BatchOperationData,
    BatchOperationResponse,
    MoneyAmount,
    RequestId,
    SuccessResponse,
    UtcDateTime,
)
from bid_system.shared.contracts.errors import ErrorCode, ErrorDetail, ErrorResponse
from bid_system.shared.contracts.pagination import PageData, PaginatedResponse, PaginationMeta

__all__ = [
    "ApiContractModel",
    "BatchItemResult",
    "BatchOperationData",
    "BatchOperationResponse",
    "ErrorCode",
    "ErrorDetail",
    "ErrorResponse",
    "MoneyAmount",
    "PageData",
    "PaginatedResponse",
    "PaginationMeta",
    "RequestId",
    "SuccessResponse",
    "UtcDateTime",
]
