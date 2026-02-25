from __future__ import annotations

from tools.base import Tool, ToolSpec

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        return self._tools[name]

    def get(self, name: str) -> Tool:
        # Backward-compatible alias.
        return self.get_tool(name)

    def list_specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    def clear(self) -> None:
        self._tools.clear()


registry = ToolRegistry()


def register_tool(tool_cls: type[Tool]) -> type[Tool]:
    registry.register(tool_cls())
    return tool_cls
