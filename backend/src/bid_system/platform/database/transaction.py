"""Request or message scoped SQLAlchemy transaction manager."""

import logging
from collections.abc import Callable
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from bid_system.platform.database.session import SessionFactory

DATABASE_LOGGER = logging.getLogger("bid_system.database")
PoolObserver = Callable[[], None]


class AsyncTransactionManager:
    """Own exactly one session and transaction for one application operation."""

    def __init__(
        self,
        session_factory: SessionFactory,
        pool_observer: PoolObserver | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._pool_observer = pool_observer
        self._session: AsyncSession | None = None

    @property
    def session_factory(self) -> SessionFactory:
        """Expose the injectable factory without creating a session eagerly."""
        return self._session_factory

    @property
    def session(self) -> AsyncSession:
        """Expose the session only to concrete infrastructure repositories."""
        if self._session is None:
            raise RuntimeError("Transaction has not been entered")
        return self._session

    async def __aenter__(self) -> "AsyncTransactionManager":
        if self._session is not None:
            raise RuntimeError("Transaction manager cannot be re-entered")
        session = self._session_factory()
        self._session = session
        try:
            await session.begin()
            self._observe_pool()
        except BaseException:
            await session.close()
            self._session = None
            raise
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        session = self.session
        try:
            if exception_type is not None:
                try:
                    await session.rollback()
                except BaseException as error:
                    self._log_failure("database.transaction.rollback_failed", error)
                    raise
            else:
                try:
                    await session.commit()
                except BaseException as error:
                    self._log_failure("database.transaction.commit_failed", error)
                    try:
                        await session.rollback()
                    except BaseException as rollback_error:
                        self._log_failure(
                            "database.transaction.rollback_failed",
                            rollback_error,
                        )
                    raise
        finally:
            await session.close()
            self._session = None
            self._observe_pool()
        return False

    def _observe_pool(self) -> None:
        if self._pool_observer is not None:
            self._pool_observer()

    @staticmethod
    def _log_failure(event_name: str, error: BaseException) -> None:
        # WHY: driver messages can contain SQL values; retain only category and traceback frames.
        safe_error = RuntimeError(f"{type(error).__qualname__}: details redacted")
        DATABASE_LOGGER.error(
            event_name,
            exc_info=(type(safe_error), safe_error, error.__traceback__),
            extra={
                "event_name": event_name,
                "error_type": type(error).__qualname__,
                "outcome": "error",
            },
        )
