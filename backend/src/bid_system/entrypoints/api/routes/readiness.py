"""Critical infrastructure readiness endpoint."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from bid_system.bootstrap.container import LifecycleResource
from bid_system.entrypoints.api.dependencies import RequestContext, get_request_context
from bid_system.entrypoints.api.responses import (
    CheckStatus,
    ReadinessResponse,
    ReadinessStatus,
    error_response,
    success_response,
)
from bid_system.shared.contracts.api import SuccessResponse
from bid_system.shared.contracts.errors import ErrorCode, ErrorDetail, ErrorResponse

router = APIRouter()


async def _probe(resource: LifecycleResource, timeout_seconds: float) -> CheckStatus:
    try:
        async with asyncio.timeout(timeout_seconds):
            await resource.probe()
    except Exception:
        # WHY: readiness is externally visible and must not expose provider errors or addresses.
        return CheckStatus.DOWN
    return CheckStatus.UP


@router.get(
    "/readiness",
    name="readiness",
    response_model=SuccessResponse[ReadinessResponse],
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
async def readiness(
    request: Request,
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> SuccessResponse[ReadinessResponse] | JSONResponse:
    """Report whether every critical application resource accepts a probe."""
    container = request.app.state.container
    timeout_seconds = container.settings.api.readiness_timeout_seconds
    resources: tuple[tuple[str, LifecycleResource], ...] = (
        ("database", container.database),
        ("redis", container.redis),
        ("object_store", container.minio),
    )
    results = await asyncio.gather(
        *(_probe(resource, timeout_seconds) for _, resource in resources)
    )
    checks = {name: result for (name, _), result in zip(resources, results, strict=True)}
    if all(result is CheckStatus.UP for result in results):
        return success_response(
            data=ReadinessResponse(status=ReadinessStatus.READY, checks=checks),
            request_id=context.request_id,
        )
    details = [
        ErrorDetail(
            location=["checks", name],
            message="依赖不可用",
            error_type="dependency_down",
        )
        for name, check_status in checks.items()
        if check_status is CheckStatus.DOWN
    ]
    return error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code=ErrorCode.SERVICE_UNAVAILABLE,
        message="关键依赖尚未就绪",
        details=details,
        request_id=context.request_id,
    )
