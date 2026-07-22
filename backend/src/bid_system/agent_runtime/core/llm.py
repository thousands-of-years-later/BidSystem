"""Provider-neutral structured model invocation contracts."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar

from pydantic import BaseModel

from bid_system.agent_runtime.context.run import RunContext

OutputModelT = TypeVar("OutputModelT", bound=BaseModel)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


class MessageRole(StrEnum):
    """Roles accepted by the provider-neutral model boundary."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """One immutable message submitted to a model provider."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        _require_non_blank(self.content, "content")


@dataclass(frozen=True, slots=True)
class StructuredOutputRequest[OutputModelT: BaseModel]:
    """Messages and the exact Pydantic schema required from the model."""

    messages: tuple[ModelMessage, ...]
    output_schema: type[OutputModelT]

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("messages must not be empty")


@dataclass(frozen=True, slots=True)
class StructuredOutputResult[OutputModelT: BaseModel]:
    """Validated candidate output paired with its immutable provenance."""

    output: OutputModelT
    context: RunContext


class ModelPort(Protocol):
    """Port implemented by concrete model-provider adapters."""

    async def generate_structured(
        self,
        request: StructuredOutputRequest[OutputModelT],
        context: RunContext,
    ) -> StructuredOutputResult[OutputModelT]: ...
