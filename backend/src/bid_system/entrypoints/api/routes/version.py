"""Application release metadata endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from bid_system import __version__
from bid_system.entrypoints.api.dependencies import RequestContext, get_request_context
from bid_system.entrypoints.api.responses import VersionResponse, success_response
from bid_system.shared.contracts.api import SuccessResponse

router = APIRouter()


@router.get("/version", name="application_version", response_model=SuccessResponse[VersionResponse])
async def application_version(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> SuccessResponse[VersionResponse]:
    """Return the deployed package version."""
    return success_response(
        data=VersionResponse(version=__version__),
        request_id=context.request_id,
    )
