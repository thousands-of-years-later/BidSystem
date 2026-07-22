"""Provider-neutral tool definition and execution policy."""

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from bid_system.agent_runtime.context.run import RunContext
from bid_system.agent_runtime.tools.response import ToolResponse

TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
DEFAULT_TOOL_MAX_ATTEMPTS = 1
DEFAULT_TOOL_RETRY_BASE_DELAY_SECONDS = 0.5
DEFAULT_TOOL_RETRY_MAX_DELAY_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Validated execution limits and retry safety for one tool."""

    name: str
    timeout_seconds: float
    max_attempts: int = DEFAULT_TOOL_MAX_ATTEMPTS
    retry_base_delay_seconds: float = DEFAULT_TOOL_RETRY_BASE_DELAY_SECONDS
    retry_max_delay_seconds: float = DEFAULT_TOOL_RETRY_MAX_DELAY_SECONDS
    idempotent: bool = False

    def __post_init__(self) -> None:
        if TOOL_NAME_PATTERN.fullmatch(self.name) is None:
            raise ValueError("name must be a lower-snake-case tool identifier")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.retry_base_delay_seconds <= 0:
            raise ValueError("retry_base_delay_seconds must be greater than zero")
        if self.retry_max_delay_seconds < self.retry_base_delay_seconds:
            raise ValueError(
                "retry_max_delay_seconds must be greater than or equal to "
                "retry_base_delay_seconds"
            )


@runtime_checkable
class Tool(Protocol):
    """Common structured boundary for explicitly registered business tools."""

    @property
    def spec(self) -> ToolSpec: ...

    @property
    def input_schema(self) -> type[BaseModel]: ...

    @property
    def output_schema(self) -> type[BaseModel]: ...

    async def invoke(
        self,
        input_data: BaseModel,
        context: RunContext,
    ) -> ToolResponse[BaseModel]: ...
