"""Redis async client lifecycle adapter."""

from redis.asyncio import Redis

from bid_system.platform.config import RedisSettings


class RedisResource:
    """Own a Redis client and its connection pool."""

    def __init__(self, settings: RedisSettings) -> None:
        self.client: Redis = Redis.from_url(
            settings.url.get_secret_value(),
            max_connections=settings.max_connections,
            decode_responses=True,
        )

    async def probe(self) -> None:
        """Fail startup unless Redis responds to PING."""
        await self.client.ping()

    async def close(self) -> None:
        """Close the client and disconnect its pool."""
        await self.client.aclose(close_connection_pool=True)


def create_redis_resource(settings: RedisSettings) -> RedisResource:
    """Construct an unconnected Redis resource."""
    return RedisResource(settings)
