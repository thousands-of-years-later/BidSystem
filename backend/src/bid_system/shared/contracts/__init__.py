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
from bid_system.shared.contracts.tasks import (
    DOCUMENT_PARSE_SCHEMA_VERSION,
    DOCUMENT_PARSE_TASK_TYPE,
    DocumentParseTaskInput,
)

__all__ = [
    "DOCUMENT_PARSE_SCHEMA_VERSION",
    "DOCUMENT_PARSE_TASK_TYPE",
    "ApiContractModel",
    "BatchItemResult",
    "BatchOperationData",
    "BatchOperationResponse",
    "DocumentParseTaskInput",
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
