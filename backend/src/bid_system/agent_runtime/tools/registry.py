"""Process-local registry with explicit registration and no dynamic loading."""

from bid_system.agent_runtime.tools.base import Tool, ToolSpec


class DuplicateToolError(ValueError):
    """Raised when registration would silently replace a tool."""


class UnknownToolError(LookupError):
    """Raised when a caller requests an unregistered tool."""


class ToolRegistry:
    """Own the fixed set of tools available to one assembled runtime."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register one tool, rejecting accidental name replacement."""
        name = tool.spec.name
        if name in self._tools:
            raise DuplicateToolError(f"Tool is already registered: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool:
        """Resolve one explicitly registered tool by stable name."""
        try:
            return self._tools[name]
        except KeyError as error:
            raise UnknownToolError(f"Tool is not registered: {name}") from error

    def list_specs(self) -> tuple[ToolSpec, ...]:
        """List available tool metadata in deterministic name order."""
        return tuple(self._tools[name].spec for name in sorted(self._tools))
