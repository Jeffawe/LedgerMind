from __future__ import annotations

import json
from datetime import date

from domain.schemas import DateRange, LedgerMindPlan, PlanAssumptions, PlanCall, PlanOutputTarget, UserRequest
from infrastructure.llm.llm_client import LLMClient
from infrastructure.policy_profile.profile import PolicyProfileStore
from logs import get_logger
from tools.base import ToolSpec

logger = get_logger("PlannerLLM")


class PlannerLLM:
    """Builds planner prompts and parses strict JSON plan outputs from an LLM."""

    def __init__(
        self,
        llm_client: LLMClient,
        policy_profiles: PolicyProfileStore | None = None,
        preferred_fallback_tools: list[str] | None = None,
    ):
        self._llm = llm_client
        self._policy_profiles = policy_profiles or PolicyProfileStore()
        self._preferred_fallback_tools = list(preferred_fallback_tools or [])

    def build_prompt(self, request: UserRequest, tools: list[ToolSpec]) -> str:
        tool_catalog = [
            {
                "name": tool.name,
                "description": tool.description,
                "args_schema": tool.args_schema,
            }
            for tool in tools
        ]

        # Compact contract for the model: enough structure to generate valid output
        # without dumping the full Pydantic JSON Schema (which often causes schema narration).
        contract = {
            "schema": "ledgermind.plan.v1",
            "objective": "string",
            "assumptions": {
                "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
                "currency": "string|null",
            },
            "calls": [
                {
                    "id": "string",
                    "tool": "one of available_tools[].name",
                    "args": "object",
                    "purpose": "string",
                }
            ],
            "output": {
                "response_schema": "string",
                "focus": ["string"],
            },
        }
        policy_profile = self._policy_profiles.fetch_policy_profile(request.context.policy_profile)
        prompt_payload = {
            "task": "Create a tool plan for the user request.",
            "user_request": request.model_dump(),
            "policy_profile": policy_profile,
            "available_tools": tool_catalog,
            "output_contract": contract,
            "example_valid_response": {
                "schema": "ledgermind.plan.v1",
                "objective": "Review recent spending and suggest conservative improvements",
                "assumptions": {
                    "date_range": {"start": "2026-02-01", "end": "2026-02-28"},
                    "currency": "USD",
                },
                "calls": [
                    {
                        "id": "s1",
                        "tool": "ledgers.category_summary",
                        "args": {"date_range": {"start": "2026-02-01", "end": "2026-02-28"}, "currency": "USD"},
                        "purpose": "Summarize spending and income by category",
                    }
                ],
                "output": {"response_schema": "ledgermind.v1.decision_response", "focus": ["spend_reduction"]},
            },
            "rules": [
                "Return JSON only.",
                "Return exactly one JSON object. No markdown. No prose. No code fences.",
                "Use only tool names from available_tools.",
                "Prefer grounded, minimal tool calls.",
                "Do not describe or explain the schema.",
            ],
        }
        return json.dumps(prompt_payload, indent=2, default=str)

    def generate_plan(
        self,
        request: UserRequest,
        tools: list[ToolSpec],
        preferred_tool_names: list[str] | None = None,
    ) -> LedgerMindPlan:
        if not tools:
            return self._empty_plan(request, objective=request.message)

        logger.info("PlannerLLM generate_plan start tools=%d policy_profile=%s", len(tools), request.context.policy_profile)
        prompt = self.build_prompt(request, tools)
        try:
            parsed = self._llm.instruct_complete(
                prompt=prompt,
                response_model=LedgerMindPlan,
                max_retries=2,
                timeout=None,
            )
        except Exception as exc:
            logger.info("PlannerLLM structured generation failed (%s); using fallback plan", exc.__class__.__name__)
            logger.exception("PlannerLLM structured generation exception details")
            return self._fallback_plan(tools, preferred_tool_names=preferred_tool_names)

        valid_names = {tool.name for tool in tools}
        filtered_calls = [call for call in parsed.calls if call.tool in valid_names]
        if not filtered_calls:
            logger.info("PlannerLLM produced no valid calls; using fallback plan")
            return self._fallback_plan(tools, preferred_tool_names=preferred_tool_names)

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

    def _fallback_plan(self, tools: list[ToolSpec], preferred_tool_names: list[str] | None = None) -> LedgerMindPlan:
        valid_names = {tool.name for tool in tools}
        preferred_candidates = preferred_tool_names if preferred_tool_names is not None else self._preferred_fallback_tools
        if not preferred_candidates:
            preferred_candidates = ["ledgers.category_summary", "ledger.category_summary"]

        selected_tools: list[str] = []
        seen: set[str] = set()
        for name in preferred_candidates:
            if name in valid_names and name not in seen:
                selected_tools.append(name)
                seen.add(name)

        if not selected_tools:
            selected_tools = [tools[0].name]

        today = date.today()
        start = today.replace(day=1).isoformat()
        end = today.isoformat()
        calls = [
            PlanCall(
                id=f"s{idx}",
                tool=tool_name,
                args=self._fallback_args_for_tool(tool_name, start=start, end=end),
                purpose=self._fallback_purpose_for_tool(tool_name),
            )
            for idx, tool_name in enumerate(selected_tools, start=1)
        ]

        return LedgerMindPlan(
            schema="ledgermind.plan.v1",
            objective="Generate a grounded financial performance review and improvements plan",
            assumptions=PlanAssumptions(
                date_range=DateRange(start=today.replace(day=1), end=today),
                currency="USD",
            ),
            calls=calls,
            output=PlanOutputTarget(
                response_schema="ledgermind.v1.decision_response",
                focus=["spend_reduction", "cash_buffer"],
            ),
        )

    def _fallback_args_for_tool(self, tool_name: str, start: str, end: str) -> dict:
        start_dt = date.fromisoformat(start)
        if tool_name == "policy.check_recommendation":
            return {
                "recommendation": "Reduce discretionary spend while preserving cash buffer and essential obligations."
            }
        if tool_name == "ledgers.month_summary":
            return {
                "month_number": start_dt.month,
                "year": start_dt.year,
                "exclude_transfers": True,
            }
        return {
            "date_range": {"start": start, "end": end},
            "exclude_transfers": True,
        }

    def _fallback_purpose_for_tool(self, tool_name: str) -> str:
        purposes = {
            "ledgers.category_summary": "Compute spending and income totals by category",
            "ledger.category_summary": "Compute spending and income totals by category",
            "ledgers.month_summary": "Summarize monthly spending, income, and net cashflow",
            "detect.recurring_charges": "Detect recurring charges worth review",
            "detect.subscriptions": "Detect recurring charges worth review",
            "detect.anomalies": "Find unusually large or irregular transactions",
            "forecast.cashflow_30d": "Project near-term cashflow from recent patterns",
            "policy.check_recommendation": "Validate recommendation against policy profile",
        }
        return purposes.get(tool_name, f"Collect evidence using {tool_name}")
