"""Atomic Redis rate limiting for credential and sensitive-operation boundaries."""

import hashlib
from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from redis.exceptions import RedisError

FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RedisScriptClient(Protocol):
    """Small Redis capability required for an atomic rate-limit decision."""

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> Awaitable[int | str] | int | str: ...


class OutageMode(StrEnum):
    """Explicit availability choice when the rate-limit store fails."""

    DENY = "deny"
    ALLOW = "allow"


@dataclass(frozen=True)
class RateLimitPolicy:
    """Named fixed-window limit and its Redis outage behavior."""

    capacity: int
    window_seconds: int
    outage_mode: OutageMode

    def __post_init__(self) -> None:
        if self.capacity < 1 or self.window_seconds < 1:
            raise ValueError("Rate-limit capacity and window must be positive")


@dataclass(frozen=True)
class RateLimitDecision:
    """Externally observable rate-limit outcome."""

    allowed: bool
    remaining: int
    degraded: bool


class RateLimitKey:
    """Build bounded keys without persisting plain account identifiers."""

    @staticmethod
    def login(*, client_ip: str, account_identifier: str) -> str:
        normalized_identifier = account_identifier.strip().casefold()
        if not client_ip.strip() or not normalized_identifier:
            raise ValueError("Login rate-limit key inputs must not be blank")
        identifier_digest = hashlib.sha256(normalized_identifier.encode("utf-8")).hexdigest()
        return f"security:rate:login:{client_ip}:{identifier_digest}"

    @staticmethod
    def sensitive(*, tenant_id: str, actor_id: str, action: str) -> str:
        values = (tenant_id, actor_id, action)
        if any(not value.strip() for value in values):
            raise ValueError("Sensitive rate-limit key inputs must not be blank")
        return f"security:rate:sensitive:{tenant_id}:{actor_id}:{action}"

    @staticmethod
    def refresh(*, client_ip: str, token_digest: str) -> str:
        if not client_ip.strip() or not token_digest.strip():
            raise ValueError("Refresh rate-limit key inputs must not be blank")
        return f"security:rate:refresh:{client_ip}:{token_digest}"


class RedisRateLimiter:
    """Execute one atomic fixed-window count for each security decision."""

    def __init__(self, client: RedisScriptClient) -> None:
        self._client = client

    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitDecision:
        if not key.strip():
            raise ValueError("Rate-limit key must not be blank")
        try:
            evaluation = self._client.eval(
                FIXED_WINDOW_SCRIPT,
                1,
                key,
                str(policy.window_seconds),
            )
            raw_count = (
                evaluation if isinstance(evaluation, (int, str)) else await evaluation
            )
            count = int(raw_count)
        except (RedisError, TimeoutError):
            allowed = policy.outage_mode is OutageMode.ALLOW
            return RateLimitDecision(allowed=allowed, remaining=0, degraded=True)
        remaining = max(policy.capacity - count, 0)
        return RateLimitDecision(
            allowed=count <= policy.capacity,
            remaining=remaining,
            degraded=False,
        )
