from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from kombu import Connection, Queue

class AsyncResult(Protocol):
    def failed(self) -> bool: ...
    def successful(self) -> bool: ...

class Task:
    autoretry_for: tuple[type[BaseException], ...]
    max_retries: int
    retry_backoff: int
    retry_backoff_max: int
    retry_jitter: bool

    def apply(
        self,
        *,
        kwargs: Mapping[str, str],
        throw: bool,
    ) -> AsyncResult: ...

class CeleryConfig:
    accept_content: tuple[str, ...]
    broker_connection_retry: bool
    broker_connection_retry_on_startup: bool
    broker_transport_options: dict[str, bool]
    enable_utc: bool
    result_backend: str | None
    task_acks_late: bool
    task_acks_on_failure_or_timeout: bool
    task_always_eager: bool
    task_default_delivery_mode: str
    task_default_exchange: str
    task_default_queue: str
    task_default_routing_key: str
    task_eager_propagates: bool
    task_ignore_result: bool
    task_publish_retry: bool
    task_publish_retry_policy: dict[str, int | float]
    task_queues: tuple[Queue, ...]
    task_reject_on_worker_lost: bool
    task_routes: dict[str, dict[str, str]]
    task_serializer: str
    task_soft_time_limit: int
    task_time_limit: int
    timezone: str
    worker_cancel_long_running_tasks_on_connection_loss: bool
    worker_concurrency: int
    worker_detect_quorum_queues: bool
    worker_enable_remote_control: bool
    worker_hijack_root_logger: bool
    worker_dead_letter_queue: Queue
    worker_prefetch_multiplier: int

class Celery:
    main: str
    conf: CeleryConfig
    tasks: Mapping[str, Task]

    def __init__(self, main: str, *, broker: str) -> None: ...
    def connection_for_write(self) -> Connection: ...
    def task[**ParametersT, ReturnT](
        self,
        *,
        name: str,
        typing: bool,
        autoretry_for: tuple[type[BaseException], ...] = ...,
        max_retries: int = ...,
        retry_backoff: int = ...,
        retry_backoff_max: int = ...,
        retry_jitter: bool = ...,
    ) -> Callable[
        [Callable[ParametersT, ReturnT]],
        Callable[ParametersT, ReturnT],
    ]: ...
    def worker_main(self, argv: Sequence[str]) -> None: ...
