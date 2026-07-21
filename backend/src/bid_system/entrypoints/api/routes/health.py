"""Process liveness endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from bid_system.entrypoints.api.dependencies import RequestContext, get_request_context
from bid_system.entrypoints.api.responses import (
    HealthResponse,
    LivenessStatus,
    success_response,
)
from bid_system.shared.contracts.api import SuccessResponse

router = APIRouter()


@router.get("/health", name="health", response_model=SuccessResponse[HealthResponse])
async def health(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> SuccessResponse[HealthResponse]:
    """Report liveness without touching external dependencies."""
    return success_response(
        data=HealthResponse(status=LivenessStatus.ALIVE),
        request_id=context.request_id,
    )
