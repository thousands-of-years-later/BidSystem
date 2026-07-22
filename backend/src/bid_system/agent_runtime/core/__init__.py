"""Core model invocation contracts."""

from bid_system.agent_runtime.core.llm import (
    MessageRole,
    ModelMessage,
    ModelPort,
    StructuredOutputRequest,
    StructuredOutputResult,
)

__all__ = [
    "MessageRole",
    "ModelMessage",
    "ModelPort",
    "StructuredOutputRequest",
    "StructuredOutputResult",
]
