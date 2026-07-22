"""Per-process async resource lifecycle for synchronous Celery task boundaries."""

import asyncio
import atexit
import threading
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

from bid_system.bootstrap.container import ApplicationContainer
from bid_system.platform.config import AppSettings

ResultT = TypeVar("ResultT")
ContainerFactory = Callable[[AppSettings], ApplicationContainer]
AsyncOperation = Callable[[ApplicationContainer], Awaitable[ResultT]]


class WorkerRuntimeState(StrEnum):
    """Lifecycle states for one Celery pool process."""

    NEW = "new"
    STARTED = "started"
    CLOSED = "closed"


def _default_container_factory(settings: AppSettings) -> ApplicationContainer:
    return ApplicationContainer(settings)


async def _await_operation[OperationResultT](
    operation: Awaitable[OperationResultT],
) -> OperationResultT:
    return await operation


class WorkerRuntime:
    """Reuse one asyncio loop and bootstrap container inside each pool process."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        container_factory: ContainerFactory = _default_container_factory,
    ) -> None:
        self.settings = settings
        self._container_factory = container_factory
        self._runner: asyncio.Runner | None = None
        self._container: ApplicationContainer | None = None
        self._state = WorkerRuntimeState.NEW
        self._lock = threading.Lock()

    @property
    def state(self) -> WorkerRuntimeState:
        return self._state

    def run(self, operation: AsyncOperation[ResultT]) -> ResultT:
        """Execute one async use case on the process-owned event loop."""
        with self._lock:
            container = self._ensure_started()
            runner = self._require_runner()
            return runner.run(_await_operation(operation(container)))

    def close(self) -> None:
        """Close resources idempotently during Celery warm shutdown or process exit."""
        with self._lock:
            if self._state is WorkerRuntimeState.CLOSED:
                return
            runner = self._runner
            container = self._container
            try:
                if runner is not None and container is not None:
                    runner.run(container.close())
            finally:
                if runner is not None:
                    runner.close()
                self._runner = None
                self._container = None
                self._state = WorkerRuntimeState.CLOSED

    def _ensure_started(self) -> ApplicationContainer:
        if self._state is WorkerRuntimeState.CLOSED:
            raise RuntimeError("Worker runtime is closed")
        if self._state is WorkerRuntimeState.STARTED:
            if self._container is None:
                raise RuntimeError("Started worker runtime has no container")
            return self._container

        # WHY: Celery prefork children must not inherit live sockets created by the parent.
        runner = asyncio.Runner()
        container = self._container_factory(self.settings)
        try:
            runner.run(container.start())
        except BaseException:
            runner.close()
            raise
        self._runner = runner
        self._container = container
        self._state = WorkerRuntimeState.STARTED
        return container

    def _require_runner(self) -> asyncio.Runner:
        if self._runner is None:
            raise RuntimeError("Worker runtime event loop is unavailable")
        return self._runner


def register_process_cleanup(runtime: WorkerRuntime) -> None:
    """Register best-effort cleanup without opening resources during module import."""
    atexit.register(runtime.close)
