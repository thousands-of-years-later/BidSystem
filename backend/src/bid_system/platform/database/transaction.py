"""Request or message scoped SQLAlchemy transaction manager."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from bid_system.platform.database.session import SessionFactory


class AsyncTransactionManager:
    """Own exactly one session and transaction for one application operation."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
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
                await session.rollback()
            else:
                try:
                    await session.commit()
                except BaseException:
                    await session.rollback()
                    raise
        finally:
            await session.close()
            self._session = None
        return False
