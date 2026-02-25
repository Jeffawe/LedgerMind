from __future__ import annotations

import json
import unittest

from application.planner import PlannerService
from domain.schemas import LedgerMindPlan, UserRequest, UserRequestContext
from llm.planner import PlannerLLM
from tools.registry import registry


class _StubLLMClient:
    def __init__(self, response: str):
        self._response = response

    def complete(self, prompt: str) -> str:
        return self._response


class PlannerLLMTests(unittest.TestCase):
    def setUp(self) -> None:
        import tools  # noqa: F401

    def _request(self) -> UserRequest:
        return UserRequest(
            request_id="req_test_001",
            user_id="u_123",
            message="How did I do last month and what should I change?",
            context=UserRequestContext(timezone="America/New_York", policy_profile="default_v1"),
        )

    def test_generate_plan_from_valid_llm_json(self) -> None:
        payload = {
            "schema": "ledgermind.plan.v1",
            "objective": "Understand last month performance and suggest improvements",
            "assumptions": {
                "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
                "currency": "USD",
            },
            "calls": [
                {
                    "id": "s1",
                    "tool": "ledger.category_summary",
                    "args": {
                        "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
                        "exclude_transfers": True,
                    },
                    "purpose": "Compute spending and income totals by category",
                }
            ],
            "output": {
                "response_schema": "ledgermind.v1.decision_response",
                "focus": ["spend_reduction", "subscription_cleanup", "cash_buffer"],
            },
        }
        planner_llm = PlannerLLM(_StubLLMClient(json.dumps(payload)))

        plan = planner_llm.generate_plan(self._request(), registry.list_specs())

        self.assertEqual(plan.schema_version, "ledgermind.plan.v1")
        self.assertEqual(len(plan.calls), 1)
        self.assertEqual(plan.calls[0].tool, "ledger.category_summary")

    def test_generate_plan_falls_back_on_invalid_output(self) -> None:
        planner_llm = PlannerLLM(_StubLLMClient("not-json"))

        plan = planner_llm.generate_plan(self._request(), registry.list_specs())

        self.assertGreaterEqual(len(plan.calls), 1)
        self.assertTrue(plan.calls[0].tool)

    def test_build_prompt_includes_policy_profile(self) -> None:
        planner_llm = PlannerLLM(_StubLLMClient("{}"))
        prompt = planner_llm.build_prompt(self._request(), registry.list_specs())
        payload = json.loads(prompt)

        self.assertIn("policy_profile", payload)
        self.assertEqual(payload["policy_profile"]["id"], "default_v1")
        self.assertEqual(payload["policy_profile"]["risk_tolerance"], "conservative")

    def test_planner_service_returns_plan_schema(self) -> None:
        payload = {
            "schema": "ledgermind.plan.v1",
            "objective": "Review category totals",
            "assumptions": {"currency": "USD"},
            "calls": [
                {
                    "id": "s1",
                    "tool": "ledger.category_summary",
                    "args": {
                        "currency": "USD",
                    },
                    "purpose": "Summarize category totals",
                }
            ],
            "output": {
                "response_schema": "ledgermind.v1.decision_response",
                "focus": ["spend_reduction"],
            },
        }
        planner_service = PlannerService(
            registry=registry,
            planner_llm=PlannerLLM(_StubLLMClient(json.dumps(payload))),
        )

        plan = planner_service.plan(self._request())

        self.assertEqual(plan.schema_version, "ledgermind.plan.v1")
        self.assertEqual(len(plan.calls), 1)
        self.assertEqual(plan.calls[0].tool, "ledger.category_summary")
        self.assertEqual(plan.output.response_schema, "ledgermind.v1.decision_response")

    def test_sample_plan_schema_validates(self) -> None:
        sample = {
            "schema": "ledgermind.plan.v1",
            "objective": "Understand last month performance and suggest improvements",
            "assumptions": {
                "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
                "currency": "USD",
            },
            "calls": [
                {
                    "id": "s1",
                    "tool": "ledger.category_summary",
                    "args": {
                        "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
                        "exclude_transfers": True,
                    },
                    "purpose": "Compute spending and income totals by category",
                },
                {
                    "id": "s2",
                    "tool": "detect.subscriptions",
                    "args": {
                        "date_range": {"start": "2025-11-01", "end": "2026-01-31"},
                        "min_occurrences": 2,
                        "tolerance_days": 5,
                    },
                    "purpose": "Identify recurring subscriptions to optimize",
                },
            ],
            "output": {
                "response_schema": "ledgermind.v1.decision_response",
                "focus": ["spend_reduction", "subscription_cleanup", "cash_buffer"],
            },
        }
        plan = LedgerMindPlan.model_validate(sample)
        self.assertEqual(len(plan.calls), 2)
        self.assertEqual(plan.calls[1].tool, "detect.subscriptions")


if __name__ == "__main__":
    unittest.main()
