"""Redis-backed security rate-limit behavior tests."""

import pytest
from redis.exceptions import RedisError

from bid_system.platform.security.rate_limit import (
    OutageMode,
    RateLimitKey,
    RateLimitPolicy,
    RedisRateLimiter,
)


class FakeRedisScriptClient:
    def __init__(self, results: list[int] | None = None, error: RedisError | None = None) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[tuple[str, int, tuple[str, ...]]] = []

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> int:
        self.calls.append((script, numkeys, keys_and_args))
        if self.error is not None:
            raise self.error
        return self.results.pop(0)


def test_login_key_never_contains_plain_identifier() -> None:
    key = RateLimitKey.login(client_ip="192.0.2.1", account_identifier="User@Example.test")

    assert key.startswith("security:rate:login:192.0.2.1:")
    assert "user@example.test" not in key.lower()


@pytest.mark.asyncio
async def test_allows_until_atomic_redis_counter_exceeds_capacity() -> None:
    client = FakeRedisScriptClient(results=[1, 4])
    limiter = RedisRateLimiter(client)
    policy = RateLimitPolicy(capacity=3, window_seconds=60, outage_mode=OutageMode.DENY)

    first = await limiter.check("security:rate:test", policy)
    exhausted = await limiter.check("security:rate:test", policy)

    assert first.allowed is True
    assert first.remaining == 2
    assert exhausted.allowed is False
    assert exhausted.remaining == 0
    assert client.calls[0][1:] == (1, ("security:rate:test", "60"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,allowed",
    ((OutageMode.DENY, False), (OutageMode.ALLOW, True)),
)
async def test_redis_outage_obeys_explicit_policy(mode: OutageMode, allowed: bool) -> None:
    limiter = RedisRateLimiter(FakeRedisScriptClient(error=RedisError("unavailable")))

    decision = await limiter.check(
        "security:rate:test",
        RateLimitPolicy(capacity=3, window_seconds=60, outage_mode=mode),
    )

    assert decision.allowed is allowed
    assert decision.degraded is True
