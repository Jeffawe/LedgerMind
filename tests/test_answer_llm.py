from __future__ import annotations

import json
import unittest

from domain.schemas import LedgerMindPlan, PlanAssumptions, PlanCall, PlanOutputTarget, ToolContext, ToolResponse, UserRequest, UserRequestContext
from llm.answer_llm import AnswerLLM


class _StubLLMClient:
    def __init__(self, response: str):
        self._response = response

    def complete(self, prompt: str) -> str:
        return self._response


class AnswerLLMTests(unittest.TestCase):
    def _request(self) -> UserRequest:
        return UserRequest(
            request_id="req_001",
            user_id="u_123",
            message="How did I do last month and what should I change?",
            context=UserRequestContext(timezone="America/New_York", policy_profile="default_v1"),
        )

    def _plan(self) -> LedgerMindPlan:
        return LedgerMindPlan(
            schema="ledgermind.plan.v1",
            objective="Understand last month performance and suggest improvements",
            assumptions=PlanAssumptions(currency="USD"),
            calls=[
                PlanCall(
                    id="s1",
                    tool="ledger.category_summary",
                    args={"date_range": {"start": "2026-01-01", "end": "2026-01-31"}},
                    purpose="Compute spending and income totals by category",
                )
            ],
            output=PlanOutputTarget(
                response_schema="ledgermind.v1.decision_response",
                focus=["spend_reduction"],
            ),
        )

    def _evidence(self) -> list[ToolResponse]:
        ctx = ToolContext(
            user_id="u_123",
            ledger_id="ldg_main",
            timezone="America/New_York",
            policy_profile="default_v1",
        )
        return [
            ToolResponse(
                request_id="req_001:s1",
                tool="ledger.category_summary",
                result={"groceries": 412.55, "rent": 1800.0},
                context=ctx,
            )
        ]

    def test_generate_answer_from_valid_llm_json(self) -> None:
        payload = {
            "schema": "ledgermind.answer.v1",
            "summary": {"headline": "Headline", "bullets": ["b1"]},
            "supporting_numbers": [
                {
                    "id": "n1",
                    "label": "Net",
                    "value": 100.0,
                    "unit": "USD",
                    "type": "evidence",
                    "evidence_ref": {"citation_id": "c1", "path": "data.net"},
                }
            ],
            "options": [],
            "recommended_action": {
                "title": "Do X",
                "next_7_days": [],
                "next_30_days": [],
                "policy_alignment": [
                    {"rule": "Maintain minimum checking balance", "status": "pass", "details": "ok"}
                ],
            },
            "risks_and_tradeoffs": [],
            "assumptions_and_confidence": {
                "assumptions": [],
                "confidence": 0.8,
                "confidence_reasoning": ["grounded"],
            },
            "trace": {
                "plan_id": "plan_001",
                "tool_calls_used": ["ledger.category_summary"],
                "validation_targets": ["schema_valid"],
            },
        }
        llm = AnswerLLM(_StubLLMClient(json.dumps(payload)))
        answer = llm.generate_answer(self._request(), self._plan(), self._evidence())

        self.assertEqual(answer.schema_version, "ledgermind.answer.v1")
        self.assertEqual(answer.summary.headline, "Headline")

    def test_generate_answer_falls_back_when_invalid(self) -> None:
        llm = AnswerLLM(_StubLLMClient("not-json"))
        answer = llm.generate_answer(self._request(), self._plan(), self._evidence())

        self.assertEqual(answer.schema_version, "ledgermind.answer.v1")
        self.assertTrue(answer.recommended_action.title)
        self.assertIn("ledger.category_summary", answer.trace.tool_calls_used)

    def test_build_prompt_includes_policy_profile(self) -> None:
        llm = AnswerLLM(_StubLLMClient("{}"))
        prompt = llm.build_prompt(self._request(), self._plan(), self._evidence())
        payload = json.loads(prompt)

        self.assertIn("policy_profile", payload)
        self.assertEqual(payload["policy_profile"]["id"], "default_v1")
        self.assertIn("rules", payload["policy_profile"])


if __name__ == "__main__":
    unittest.main()
