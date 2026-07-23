from types import TracebackType
from typing import Self

class Channel: ...

class Connection:
    default_channel: Channel

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

class Exchange:
    name: str
    type: str
    durable: bool

    def __init__(self, name: str, *, type: str, durable: bool) -> None: ...

class Queue:
    name: str
    exchange: Exchange
    routing_key: str
    durable: bool
    queue_arguments: dict[str, str | int]

    def __init__(
        self,
        name: str,
        *,
        exchange: Exchange,
        routing_key: str,
        durable: bool,
        queue_arguments: dict[str, str | int],
    ) -> None: ...
    def declare(self, *, channel: Channel) -> None: ...
