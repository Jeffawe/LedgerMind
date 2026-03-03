from __future__ import annotations

from domain.schemas import (
    AnswerTrace,
    EngineAnswer,
    EvidenceRef,
    LLMAnswerDraft,
    LedgerMindPlan,
    NumericEvidence,
    ToolResponse,
    UserRequest,
)
from infrastructure.llm.llm_client import LLMClient
from infrastructure.persistence.memory_store import MemoryStore
from llm.answer_llm import AnswerLLM
from logs import get_logger

logger = get_logger("AnswerService")


class AnswerService:
    """Builds the final structured CFO answer from tool evidence."""

    def __init__(self, answer_llm: AnswerLLM | None = None, memory_store: MemoryStore | None = None):
        self._answer_llm = answer_llm or AnswerLLM(LLMClient())
        self._memory_store = memory_store or MemoryStore()

    def compose(self, request: UserRequest, plan: LedgerMindPlan, evidence: list[ToolResponse]) -> EngineAnswer:
        logger.info("AnswerService compose request_id=%s plan_calls=%d evidence=%d", request.request_id, len(plan.calls), len(evidence))
        memory_context = self._memory_store.load_recent(limit=50)
        draft = self._answer_llm.generate_draft(request, plan, evidence, memory_context=memory_context)
        answer = self._assemble_answer(request, plan, evidence, draft)
        if answer.memory:
            self._memory_store.append(answer.memory)
        return answer

    def _assemble_answer(
        self,
        request: UserRequest,
        plan: LedgerMindPlan,
        evidence: list[ToolResponse],
        draft: LLMAnswerDraft,
    ) -> EngineAnswer:
        supporting_numbers = self._build_supporting_numbers(evidence)
        trace = self._build_trace(request_id=request.request_id, evidence=evidence, draft=draft)
        return EngineAnswer(
            schema="ledgermind.answer.v1",
            answer=draft.answer,
            bullets=draft.bullets,
            supporting_numbers=supporting_numbers,
            options=draft.options,
            recommended_action=draft.recommended_action,
            risks_and_tradeoffs=draft.risks_and_tradeoffs,
            assumptions_and_confidence=draft.assumptions_and_confidence,
            trace=trace,
            memory=draft.memory,
        )

    def _build_trace(self, request_id: str, evidence: list[ToolResponse], draft: LLMAnswerDraft) -> AnswerTrace:
        available = {item.tool for item in evidence}
        requested = [name for name in draft.used_tool_calls if name in available]
        used = requested or [item.tool for item in evidence]
        return AnswerTrace(
            plan_id=request_id,
            tool_calls_used=used,
            validation_targets=["all_numbers_cited_or_assumed", "schema_valid"],
        )

    def _build_supporting_numbers(self, evidence: list[ToolResponse]) -> list[NumericEvidence]:
        numbers: list[NumericEvidence] = []
        idx = 1
        for evidence_idx, item in enumerate(evidence, start=1):
            citation_id = f"c{evidence_idx}"
            if not isinstance(item.result, dict):
                continue
            for key, value in item.result.items():
                if isinstance(value, bool):
                    continue
                if not isinstance(value, (int, float)):
                    continue
                numbers.append(
                    NumericEvidence(
                        id=f"n{idx}",
                        label=f"{str(key).replace('_', ' ').title()} ({item.tool})",
                        value=float(value),
                        unit="USD",
                        type="evidence",
                        evidence_ref=EvidenceRef(citation_id=citation_id, path=f"result.{key}"),
                    )
                )
                idx += 1
        return numbers
