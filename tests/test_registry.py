from __future__ import annotations

import unittest
from domain.schemas import ToolRequest, ToolResponse
from tools.registry import ToolRegistry


class _FakeTool:
    name = "fake_tool"

    def run(self, request: ToolRequest) -> ToolResponse:
        return ToolResponse(
            request_id=request.request_id,
            tool=self.name,
            result={"echo": request.args},
            context=request.context,
        )


class ToolRegistryTests(unittest.TestCase):
    def test_tool_request_schema_shape(self) -> None:
        payload = {
            "request_id": "req_01HZYQ3",
            "tool": "ledger.category_summary",
            "args": {
                "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
                "group_by": "category",
                "filters": {"accounts": ["checking"], "exclude_transfers": True},
                "currency": "USD",
            },
            "context": {
                "user_id": "u_123",
                "ledger_id": "ldg_main",
                "timezone": "America/New_York",
                "policy_profile": "default_v1",
            },
        }
        request = ToolRequest.model_validate(payload)
        self.assertEqual(request.tool, "ledger.category_summary")
        self.assertEqual(request.args["date_range"]["start"], "2026-01-01")
        self.assertEqual(request.context.ledger_id, "ldg_main")

    def test_register_and_get_tool(self) -> None:
        registry = ToolRegistry()
        tool = _FakeTool()
        registry.register(tool)

        result = registry.get("fake_tool")
        self.assertIs(result, tool)

    def test_get_missing_tool_raises_key_error(self) -> None:
        registry = ToolRegistry()

        with self.assertRaises(KeyError):
            registry.get("missing")

    def test_builtin_tools_self_register_on_import(self) -> None:
        from tools.registry import registry as global_registry

        import tools  # noqa: F401
        specs = global_registry.list_specs()
        names = {spec.name for spec in specs}

        self.assertIn("ledger.category_summary", names)
        self.assertIn("detect.subscriptions", names)


if __name__ == "__main__":
    unittest.main()
