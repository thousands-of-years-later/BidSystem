from collections.abc import Callable, Mapping, Sequence

class Task: ...

class CeleryConfig:
    accept_content: tuple[str, ...]
    broker_connection_retry: bool
    broker_connection_retry_on_startup: bool
    broker_transport_options: dict[str, int]
    enable_utc: bool
    result_backend: str | None
    task_acks_late: bool
    task_acks_on_failure_or_timeout: bool
    task_default_queue: str
    task_ignore_result: bool
    task_routes: dict[str, dict[str, str]]
    task_serializer: str
    task_soft_time_limit: int
    task_time_limit: int
    timezone: str
    worker_cancel_long_running_tasks_on_connection_loss: bool
    worker_concurrency: int
    worker_hijack_root_logger: bool
    worker_prefetch_multiplier: int

class Celery:
    main: str
    conf: CeleryConfig
    tasks: Mapping[str, Task]

    def __init__(self, main: str, *, broker: str) -> None: ...
    def task[**ParametersT, ReturnT](
        self,
        *,
        name: str,
        typing: bool,
    ) -> Callable[
        [Callable[ParametersT, ReturnT]],
        Callable[ParametersT, ReturnT],
    ]: ...
    def worker_main(self, argv: Sequence[str]) -> None: ...
