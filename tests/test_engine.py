from __future__ import annotations

import unittest

from application.answer import AnswerService
from application.engine import LedgerMindEngine
from application.planner import PlannerService
from application.tool_executor import ToolExecutor
from application.validator import ValidatorService
from domain.schemas import UserRequest, UserRequestContext
from tools.registry import registry


class LedgerMindEngineTests(unittest.TestCase):
    def _build_engine(self) -> LedgerMindEngine:
        import tools  # noqa: F401

        return LedgerMindEngine(
            planner=PlannerService(registry=registry),
            tool_executor=ToolExecutor(registry),
            answer_service=AnswerService(),
            validator=ValidatorService(),
        )

    def test_engine_returns_structured_answer(self) -> None:
        engine = self._build_engine()
        request = UserRequest(
            request_id="req_test_001",
            user_id="u_test",
            message="How am I spending this month?",
            context=UserRequestContext(timezone="America/New_York", policy_profile="default_v1"),
        )

        answer, issues = engine.run(request)

        self.assertEqual(answer.schema_version, "ledgermind.answer.v1")
        self.assertTrue(answer.summary.headline)
        self.assertIn("ledger.category_summary", answer.trace.tool_calls_used)
        self.assertGreaterEqual(len(answer.options), 2)
        self.assertTrue(answer.recommended_action.title)
        self.assertIsInstance(answer.supporting_numbers, list)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
