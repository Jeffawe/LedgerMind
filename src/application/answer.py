from __future__ import annotations

import logging

from domain.schemas import EngineAnswer, LedgerMindPlan, ToolResponse, UserRequest
from infrastructure.llm.llm_client import LLMClient
from llm.answer_llm import AnswerLLM

logger = logging.getLogger(__name__)


class AnswerService:
    """Builds the final structured CFO answer from tool evidence."""

    def __init__(self, answer_llm: AnswerLLM | None = None):
        self._answer_llm = answer_llm or AnswerLLM(LLMClient())

    def compose(self, request: UserRequest, plan: LedgerMindPlan, evidence: list[ToolResponse]) -> EngineAnswer:
        logger.info("AnswerService compose request_id=%s plan_calls=%d evidence=%d", request.request_id, len(plan.calls), len(evidence))
        return self._answer_llm.generate_answer(request, plan, evidence)
