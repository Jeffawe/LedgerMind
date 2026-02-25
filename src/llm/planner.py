from __future__ import annotations

import json
import logging
from datetime import date

from domain.schemas import DateRange, LedgerMindPlan, PlanAssumptions, PlanCall, PlanOutputTarget, UserRequest
from infrastructure.llm.llm_client import LLMClient
from infrastructure.policy_profile.profile import PolicyProfileStore
from tools.base import ToolSpec


logger = logging.getLogger(__name__)


class PlannerLLM:
    """Builds planner prompts and parses strict JSON plan outputs from an LLM."""

    def __init__(self, llm_client: LLMClient, policy_profiles: PolicyProfileStore | None = None):
        self._llm = llm_client
        self._policy_profiles = policy_profiles or PolicyProfileStore()

    def build_prompt(self, request: UserRequest, tools: list[ToolSpec]) -> str:
        tool_catalog = [
            {
                "name": tool.name,
                "description": tool.description,
                "args_schema": tool.args_schema,
            }
            for tool in tools
        ]

        contract = LedgerMindPlan.model_json_schema()
        policy_profile = self._policy_profiles.fetch_policy_profile(request.context.policy_profile)
        prompt_payload = {
            "task": "Create a tool plan for the user request.",
            "user_request": request.model_dump(),
            "policy_profile": policy_profile,
            "available_tools": tool_catalog,
            "output_contract": contract,
            "rules": [
                "Return JSON only.",
                "Use only tool names from available_tools.",
                "Prefer grounded, minimal tool calls.",
            ],
        }
        return json.dumps(prompt_payload, indent=2, default=str)

    def generate_plan(self, request: UserRequest, tools: list[ToolSpec]) -> LedgerMindPlan:
        if not tools:
            return self._empty_plan(request, objective=request.message)

        logger.info("PlannerLLM generate_plan start tools=%d policy_profile=%s", len(tools), request.context.policy_profile)
        prompt = self.build_prompt(request, tools)
        raw = self._llm.complete(prompt).strip()

        if not raw:
            logger.info("PlannerLLM empty response; using fallback plan")
            return self._fallback_plan(tools)

        try:
            parsed = LedgerMindPlan.model_validate_json(raw)
        except Exception:
            logger.info("PlannerLLM invalid JSON; using fallback plan")
            return self._fallback_plan(tools)

        valid_names = {tool.name for tool in tools}
        filtered_calls = [call for call in parsed.calls if call.tool in valid_names]
        if not filtered_calls:
            logger.info("PlannerLLM produced no valid calls; using fallback plan")
            return self._fallback_plan(tools)

        parsed.calls = filtered_calls
        logger.info("PlannerLLM accepted plan calls=%d", len(parsed.calls))
        return parsed

    def _empty_plan(self, request: UserRequest, objective: str) -> LedgerMindPlan:
        return LedgerMindPlan(
            objective=objective,
            assumptions=PlanAssumptions(currency="USD"),
            calls=[],
            output=PlanOutputTarget(
                response_schema="ledgermind.v1.decision_response",
                focus=["spend_reduction"],
            ),
        )

    def _fallback_plan(self, tools: list[ToolSpec]) -> LedgerMindPlan:
        preferred = "ledger.category_summary"
        valid_names = {tool.name for tool in tools}
        selected = preferred if preferred in valid_names else tools[0].name
        today = date.today()

        return LedgerMindPlan(
            schema="ledgermind.plan.v1",
            objective="Generate a grounded financial performance review and improvements plan",
            assumptions=PlanAssumptions(
                date_range=DateRange(start=today.replace(day=1), end=today),
                currency="USD",
            ),
            calls=[
                PlanCall(
                    id="s1",
                    tool=selected,
                    args={
                        "date_range": {
                            "start": today.replace(day=1).isoformat(),
                            "end": today.isoformat(),
                        },
                        "exclude_transfers": True,
                    },
                    purpose="Compute spending and income totals by category",
                )
            ],
            output=PlanOutputTarget(
                response_schema="ledgermind.v1.decision_response",
                focus=["spend_reduction", "cash_buffer"],
            ),
        )
