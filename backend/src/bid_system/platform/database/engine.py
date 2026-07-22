"""SQLAlchemy async engine lifecycle adapter."""

from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bid_system.platform.config import DatabaseSettings
from bid_system.platform.database.health import probe_database
from bid_system.platform.database.session import create_session_factory
from bid_system.platform.database.transaction import AsyncTransactionManager
from bid_system.platform.telemetry.metrics import DatabasePoolMeasurement, get_metrics_sink

PRIMARY_POOL_NAME = "primary"


@runtime_checkable
class PoolMetricsSource(Protocol):
    """Queue-pool state exposed by SQLAlchemy without leaking the concrete pool type."""

    def size(self) -> int: ...

    def checkedout(self) -> int: ...

    def overflow(self) -> int: ...


class DatabaseResource:
    """Own an async SQLAlchemy engine and its connection pool."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.engine: AsyncEngine = create_async_engine(
            settings.url.get_secret_value(),
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout_seconds,
            pool_pre_ping=True,
        )
        # WHY: ``client`` is retained while bootstrap callers migrate to the explicit engine name.
        self.client: AsyncEngine = self.engine
        self.session_factory: async_sessionmaker[AsyncSession] = create_session_factory(self.engine)

    async def probe(self) -> None:
        """Fail startup unless PostgreSQL accepts a simple query."""
        await probe_database(self.engine)
        self.observe_pool()

    def transaction(self) -> AsyncTransactionManager:
        """Create an operation-scoped transaction for bootstrap injection."""
        return AsyncTransactionManager(self.session_factory, self.observe_pool)

    def observe_pool(self) -> None:
        """Publish a low-cardinality snapshot after lifecycle and transaction events."""
        pool = self.engine.pool
        if not isinstance(pool, PoolMetricsSource):
            return
        get_metrics_sink().observe_database_pool(
            DatabasePoolMeasurement(
                pool_name=PRIMARY_POOL_NAME,
                size=pool.size(),
                checked_out=pool.checkedout(),
                overflow=pool.overflow(),
            )
        )

    async def close(self) -> None:
        """Dispose the engine and all pooled connections."""
        await self.engine.dispose()


def create_database_resource(settings: DatabaseSettings) -> DatabaseResource:
    """Construct an unconnected database resource."""
    return DatabaseResource(settings)
