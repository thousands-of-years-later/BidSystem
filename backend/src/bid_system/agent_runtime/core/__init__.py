"""Core agent execution and model invocation contracts."""

from bid_system.agent_runtime.core.agent import (
    RunContext,
    RunIdentity,
    RuntimeVersions,
    SkillVersion,
)
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
    "RunContext",
    "RunIdentity",
    "RuntimeVersions",
    "SkillVersion",
    "StructuredOutputRequest",
    "StructuredOutputResult",
]
