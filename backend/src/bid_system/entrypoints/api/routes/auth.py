"""Browser SPA authentication protocol mapping."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from bid_system.bootstrap.dependencies import (
    build_identity_authentication_repository,
    build_password_verifier,
    get_redis_resource,
    get_settings,
)
from bid_system.entrypoints.api.dependencies import (
    RequestContext,
    get_database_transaction,
    get_request_context,
)
from bid_system.entrypoints.api.responses import error_response, success_response
from bid_system.modules.identity.application.authenticate import (
    AuthenticateLocalAccountCommand,
    AuthenticateLocalAccountHandler,
)
from bid_system.modules.identity.application.ports import RefreshRotationStatus
from bid_system.modules.identity.application.resolve_identity import (
    ResolveIdentityHandler,
    ResolveIdentityQuery,
)
from bid_system.platform.config import AuthSettings
from bid_system.platform.database.transaction import AsyncTransactionManager
from bid_system.platform.queue.redis import RedisResource
from bid_system.platform.security.authentication import (
    AccessTokenIssuer,
    RefreshTokenDigest,
    RefreshTokenGenerator,
)
from bid_system.platform.security.rate_limit import (
    OutageMode,
    RateLimitKey,
    RateLimitPolicy,
    RedisRateLimiter,
)
from bid_system.shared.contracts.api import SuccessResponse
from bid_system.shared.contracts.errors import AuthenticationError, ErrorCode

router = APIRouter(prefix="/auth")

REFRESH_COOKIE_NAME = "bid_refresh_token"
CSRF_COOKIE_NAME = "bid_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
AUTH_COOKIE_PATH = "/api/v1/auth"
TOKEN_TYPE = "Bearer"
MAX_LOGIN_IDENTIFIER_LENGTH = 320
MAX_PASSWORD_BYTES = 1_024
LOGIN_RATE_POLICY = RateLimitPolicy(capacity=5, window_seconds=60, outage_mode=OutageMode.DENY)
REFRESH_RATE_POLICY = RateLimitPolicy(
    capacity=10,
    window_seconds=60,
    outage_mode=OutageMode.DENY,
)


class LoginRequest(BaseModel):
    """Validated local-login payload."""

    model_config = ConfigDict(extra="forbid")

    login_identifier: str = Field(min_length=1, max_length=MAX_LOGIN_IDENTIFIER_LENGTH)
    password: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1, max_length=64)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError("password exceeds supported boundary")
        return value


class AccessTokenResponse(BaseModel):
    """Short-lived bearer credential returned to SPA memory."""

    access_token: str
    token_type: str
    expires_in: int


class LogoutResponse(BaseModel):
    """Idempotent logout result."""

    logged_out: bool


def _redis_rate_limiter(request: Request) -> RedisRateLimiter:
    resource = get_redis_resource(request)
    if not isinstance(resource, RedisResource):
        raise RuntimeError("Initialized Redis resource has an unsupported type")
    return RedisRateLimiter(resource.client)


async def _enforce_limit(
    request: Request,
    *,
    key: str,
    policy: RateLimitPolicy,
) -> None:
    decision = await _redis_rate_limiter(request).check(key, policy)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(policy.window_seconds)},
        )


def _set_auth_cookies(
    response: Response,
    *,
    refresh_token: str,
    csrf_token: str,
    secure: bool,
    max_age: int,
) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=AUTH_COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path=AUTH_COOKIE_PATH,
    )


def _require_csrf(request: Request, csrf_header: str | None) -> None:
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if (
        csrf_cookie is None
        or csrf_header is None
        or not secrets.compare_digest(csrf_cookie, csrf_header)
    ):
        raise AuthenticationError


def _token_response(access_token: str, expires_in: int) -> AccessTokenResponse:
    return AccessTokenResponse(
        access_token=access_token,
        token_type=TOKEN_TYPE,
        expires_in=expires_in,
    )


def _require_auth_enabled(request: Request) -> AuthSettings:
    settings = get_settings(request).auth
    if not settings.enabled:
        raise AuthenticationError
    return settings


@router.post(
    "/login",
    name="authentication_login",
    response_model=SuccessResponse[AccessTokenResponse],
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    transaction: Annotated[AsyncTransactionManager, Depends(get_database_transaction)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> SuccessResponse[AccessTokenResponse]:
    """Authenticate a local account and create its first refresh session."""
    client_ip = context.client_ip or "unknown"
    await _enforce_limit(
        request,
        key=RateLimitKey.login(
            client_ip=client_ip,
            account_identifier=payload.login_identifier,
        ),
        policy=LOGIN_RATE_POLICY,
    )
    settings = _require_auth_enabled(request)
    generator = RefreshTokenGenerator()
    refresh_token = generator.generate()
    csrf_token = generator.generate()
    now = datetime.now(UTC)
    store = build_identity_authentication_repository(transaction)
    identity = await AuthenticateLocalAccountHandler(
        store=store,
        password_verifier=build_password_verifier(settings),
    ).handle(
        AuthenticateLocalAccountCommand(
            login_identifier=payload.login_identifier,
            password=payload.password,
            tenant_id=payload.tenant_id,
            session_id=str(uuid4()),
            family_id=str(uuid4()),
            refresh_token_digest=RefreshTokenDigest.digest(refresh_token),
            authenticated_at=now,
            idle_ttl=timedelta(seconds=settings.refresh_token_idle_ttl_seconds),
            absolute_ttl=timedelta(seconds=settings.refresh_token_absolute_ttl_seconds),
        )
    )
    access_token = AccessTokenIssuer(settings).issue(
        subject=identity.user_id,
        tenant_id=identity.tenant_id,
        session_id=identity.session_id,
        token_id=str(uuid4()),
        issued_at=now,
    )
    _set_auth_cookies(
        response,
        refresh_token=refresh_token,
        csrf_token=csrf_token,
        secure=settings.refresh_cookie_secure,
        max_age=settings.refresh_token_idle_ttl_seconds,
    )
    return success_response(
        data=_token_response(access_token, settings.access_token_ttl_seconds),
        request_id=context.request_id,
    )


@router.post("/refresh", name="authentication_refresh", response_model=None)
async def refresh(
    request: Request,
    response: Response,
    transaction: Annotated[AsyncTransactionManager, Depends(get_database_transaction)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> SuccessResponse[AccessTokenResponse] | JSONResponse:
    """Rotate one refresh token and return a new short-lived access token."""
    _require_csrf(request, csrf_header)
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token is None:
        raise AuthenticationError
    presented_digest = RefreshTokenDigest.digest(refresh_token)
    await _enforce_limit(
        request,
        key=RateLimitKey.refresh(
            client_ip=context.client_ip or "unknown",
            token_digest=presented_digest,
        ),
        policy=REFRESH_RATE_POLICY,
    )
    settings = _require_auth_enabled(request)
    generator = RefreshTokenGenerator()
    replacement_token = generator.generate()
    replacement_csrf = generator.generate()
    now = datetime.now(UTC)
    store = build_identity_authentication_repository(transaction)
    rotation = await store.rotate_refresh_session(
        presented_digest=presented_digest,
        replacement_session_id=str(uuid4()),
        replacement_digest=RefreshTokenDigest.digest(replacement_token),
        rotated_at=now,
        idle_ttl=timedelta(seconds=settings.refresh_token_idle_ttl_seconds),
    )
    if rotation.status is not RefreshRotationStatus.ROTATED or rotation.session is None:
        return error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=ErrorCode.AUTHENTICATION_REQUIRED,
            message="需要身份认证",
            request_id=context.request_id,
        )
    await transaction.session.flush()
    identity = await ResolveIdentityHandler(store).handle(
        ResolveIdentityQuery(
            user_id=rotation.session.user_id,
            tenant_id=rotation.session.tenant_id,
            session_id=rotation.session.session_id,
            resolved_at=now,
        )
    )
    access_token = AccessTokenIssuer(settings).issue(
        subject=identity.user_id,
        tenant_id=identity.tenant_id,
        session_id=identity.session_id,
        token_id=str(uuid4()),
        issued_at=now,
    )
    _set_auth_cookies(
        response,
        refresh_token=replacement_token,
        csrf_token=replacement_csrf,
        secure=settings.refresh_cookie_secure,
        max_age=settings.refresh_token_idle_ttl_seconds,
    )
    return success_response(
        data=_token_response(access_token, settings.access_token_ttl_seconds),
        request_id=context.request_id,
    )


@router.post(
    "/logout",
    name="authentication_logout",
    response_model=SuccessResponse[LogoutResponse],
)
async def logout(
    request: Request,
    response: Response,
    transaction: Annotated[AsyncTransactionManager, Depends(get_database_transaction)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> SuccessResponse[LogoutResponse]:
    """Idempotently revoke the refresh family and expire browser credentials."""
    _require_csrf(request, csrf_header)
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token is not None:
        store = build_identity_authentication_repository(transaction)
        await store.revoke_refresh_family_by_digest(
            token_digest=RefreshTokenDigest.digest(refresh_token),
            revoked_at=datetime.now(UTC),
        )
    response.delete_cookie(REFRESH_COOKIE_NAME, path=AUTH_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE_NAME, path=AUTH_COOKIE_PATH)
    return success_response(
        data=LogoutResponse(logged_out=True),
        request_id=context.request_id,
    )
