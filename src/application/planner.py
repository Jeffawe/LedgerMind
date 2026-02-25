from __future__ import annotations

import logging

from domain.schemas import LedgerMindPlan, UserRequest
from infrastructure.llm.llm_client import LLMClient
from llm.planner import PlannerLLM
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class PlannerService:
    """Maps a user question to an ordered list of tool calls."""

    def __init__(self, registry: ToolRegistry, planner_llm: PlannerLLM | None = None):
        self._registry = registry
        self._planner_llm = planner_llm or PlannerLLM(LLMClient())

    def plan(self, request: UserRequest) -> LedgerMindPlan:
        specs = self._registry.list_specs()
        logger.info("PlannerService planning request_id=%s available_tools=%d policy_profile=%s", request.request_id, len(specs), request.context.policy_profile)
        return self._planner_llm.generate_plan(request, specs)
