from collections.abc import Callable

import pytest
from pydantic import BaseModel, ConfigDict

from bid_system.agent_runtime.core.agent import RunContext
from bid_system.agent_runtime.tools.base import Tool, ToolSpec
from bid_system.agent_runtime.tools.registry import (
    DuplicateToolError,
    ToolRegistry,
    UnknownToolError,
)
from bid_system.agent_runtime.tools.response import ToolResponse


class ToolInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str


class ToolOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str


class StubTool:
    def __init__(self, name: str) -> None:
        self.spec = ToolSpec(name=name, timeout_seconds=1.0)
        self.input_schema = ToolInput
        self.output_schema = ToolOutput

    async def invoke(
        self,
        input_data: BaseModel,
        context: RunContext,
    ) -> ToolResponse[BaseModel]:
        assert isinstance(input_data, ToolInput)
        return ToolResponse.success(ToolOutput(candidate_id=f"candidate-{input_data.source_id}"))


def test_registry_registers_and_resolves_explicit_tool() -> None:
    registry = ToolRegistry()
    tool = StubTool("extract_document")

    registry.register(tool)

    assert registry.get("extract_document") is tool
    assert isinstance(tool, Tool)


def test_registry_rejects_duplicate_name_without_overwriting() -> None:
    registry = ToolRegistry()
    original = StubTool("extract_document")
    registry.register(original)

    with pytest.raises(DuplicateToolError, match="extract_document"):
        registry.register(StubTool("extract_document"))

    assert registry.get("extract_document") is original


def test_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(UnknownToolError, match="missing"):
        registry.get("missing")


def test_registry_lists_specs_in_stable_name_order() -> None:
    registry = ToolRegistry()
    registry.register(StubTool("zeta"))
    registry.register(StubTool("alpha"))

    assert tuple(spec.name for spec in registry.list_specs()) == ("alpha", "zeta")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: ToolSpec(name="bad name", timeout_seconds=1.0), "name"),
        (lambda: ToolSpec(name="valid", timeout_seconds=0.0), "timeout_seconds"),
        (lambda: ToolSpec(name="valid", timeout_seconds=1.0, max_attempts=0), "max_attempts"),
        (
            lambda: ToolSpec(
                name="valid",
                timeout_seconds=1.0,
                retry_base_delay_seconds=2.0,
                retry_max_delay_seconds=1.0,
            ),
            "retry_max_delay_seconds",
        ),
    ],
)
def test_tool_spec_rejects_invalid_execution_policy(
    factory: Callable[[], ToolSpec],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()
