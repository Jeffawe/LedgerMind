from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from application.answer import AnswerService
from domain.schemas import (
    LLMAnswerDraft,
    LedgerMindPlan,
    MemoryItem,
    PlanAssumptions,
    PlanOutputTarget,
    ToolContext,
    ToolResponse,
    UserRequest,
    UserRequestContext,
)
from infrastructure.persistence.memory_store import MemoryStore


class _StubAnswerLLM:
    def __init__(self) -> None:
        self.seen_memory_context_sizes: list[int] = []

    def generate_draft(self, request, plan, evidence, memory_context=None):
        self.seen_memory_context_sizes.append(len(memory_context or []))
        return LLMAnswerDraft(
            answer="ok",
            bullets=[],
            options=[],
            recommended_action=None,
            risks_and_tradeoffs=[],
            assumptions_and_confidence=None,
            memory=[
                MemoryItem(
                    text="User prefers concise recommendations.",
                    kind="preference",
                    source_request_id=request.request_id,
                )
            ],
            used_tool_calls=[],
        )


class MemoryFlowTests(unittest.TestCase):
    def _request(self, req_id: str) -> UserRequest:
        return UserRequest(
            request_id=req_id,
            user_id="u_1",
            message="How am I doing?",
            context=UserRequestContext(timezone="America/New_York", policy_profile="default_v1"),
        )

    def _plan(self) -> LedgerMindPlan:
        return LedgerMindPlan(
            schema="ledgermind.plan.v1",
            objective="Review spending",
            assumptions=PlanAssumptions(currency="USD"),
            calls=[],
            output=PlanOutputTarget(response_schema="ledgermind.v1.decision_response", focus=[]),
        )

    def _evidence(self) -> list[ToolResponse]:
        ctx = ToolContext(
            user_id="u_1",
            ledger_id="ldg_main",
            timezone="America/New_York",
            policy_profile="default_v1",
        )
        return [ToolResponse(request_id="r:s1", tool="ledgers.category_summary", result={}, context=ctx)]

    def test_answer_service_persists_memory_and_reuses_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_file = Path(tmpdir) / "memory.json"
            store = MemoryStore(file_path=memory_file, max_items=20)
            llm = _StubAnswerLLM()
            service = AnswerService(answer_llm=llm, memory_store=store)

            service.compose(self._request("req1"), self._plan(), self._evidence())
            service.compose(self._request("req2"), self._plan(), self._evidence())

            self.assertEqual(llm.seen_memory_context_sizes[0], 0)
            self.assertGreaterEqual(llm.seen_memory_context_sizes[1], 1)

            items = store.load_all()
            self.assertGreaterEqual(len(items), 1)
            self.assertEqual(items[0].kind, "preference")


if __name__ == "__main__":
    unittest.main()
