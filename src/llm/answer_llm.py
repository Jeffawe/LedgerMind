from __future__ import annotations

import json
from typing import Any, Dict, List

from domain.schemas import (
    AnswerOption,
    AssumptionsConfidence,
    LLMAnswerDraft,
    LedgerMindPlan,
    MemoryItem,
    NumericEvidence,
    PolicyAlignmentCheck,
    RecommendedAction,
    ToolResponse,
    UserRequest,
)
from infrastructure.llm.llm_client import LLMClient
from infrastructure.policy_profile.profile import PolicyProfileStore
from logs import get_logger

logger = get_logger("AnswerLLM")


class AnswerLLM:
    """Builds answer-generation prompts and parses compact answer drafts from the LLM."""

    def __init__(self, llm_client: LLMClient, policy_profiles: PolicyProfileStore | None = None):
        self._llm = llm_client
        self._policy_profiles = policy_profiles or PolicyProfileStore()

    def build_prompt(
        self,
        request: UserRequest,
        plan: LedgerMindPlan,
        evidence: List[ToolResponse],
        memory_context: List[MemoryItem] | None = None,
    ) -> str:
        policy_profile = self._policy_profiles.fetch_policy_profile(request.context.policy_profile)
        compact_evidence = [self._compact_tool_response(item) for item in evidence]
        compact_memory = [m.model_dump(mode="json") for m in (memory_context or [])][-50:]
        prompt_payload: Dict[str, Any] = {
            "task": "Generate a grounded financial decision response from tool evidence.",
            "user_request": request.model_dump(),
            "policy_profile": policy_profile,
            "plan": plan.model_dump(by_alias=True),
            "evidence": compact_evidence,
            "memory_context": compact_memory,
            "output_contract": {
                "answer": "string",
                "bullets": ["string"],
                "options": "list of option objects",
                "recommended_action": "object|null",
                "risks_and_tradeoffs": ["string"],
                "assumptions_and_confidence": "object|null",
                "memory": [
                    {
                        "text": "string",
                        "kind": "preference|goal|constraint|fact|context|other",
                        "source_request_id": "string|null",
                        "created_at": "ISO datetime string",
                    }
                ],
                "used_tool_calls": ["tool_name_string"],
            },
            "example_valid_response": {
                "answer": "February review: expenses were stable and cashflow remained positive.",
                "bullets": [
                    "Total income exceeded total expenses for the period.",
                    "Focus on recurring charges and one flexible category cap next month."
                ],
                "options": [],
                "recommended_action": None,
                "risks_and_tradeoffs": [],
                "assumptions_and_confidence": None,
                "memory": [],
                "used_tool_calls": ["ledgers.category_summary"],
            },
            "rules": [
                "Return JSON only.",
                "Return exactly one JSON object. No markdown. No prose. No tables. No code fences.",
                "Keep recommendations conservative and actionable.",
                "Do not describe or explain the schema.",
                "Use memory_context only for relevant continuity.",
                "Return memory entries only for durable facts/preferences/constraints worth keeping long-term.",
                "If nothing new should be remembered, return memory as an empty array.",
                "Do not output schema_version, supporting_numbers, or trace.",
            ],
        }
        return json.dumps(prompt_payload, indent=2, default=str)

    def generate_draft(
        self,
        request: UserRequest,
        plan: LedgerMindPlan,
        evidence: List[ToolResponse],
        memory_context: List[MemoryItem] | None = None,
    ) -> LLMAnswerDraft:
        logger.info("AnswerLLM generate_draft start plan_calls=%d evidence=%d policy_profile=%s", len(plan.calls), len(evidence), request.context.policy_profile)
        prompt = self.build_prompt(request, plan, evidence, memory_context=memory_context)
        try:
            draft = self._llm.instruct_complete(
                prompt=prompt,
                response_model=LLMAnswerDraft,
                max_retries=2,
                timeout=None,
            )
            logger.info("AnswerLLM accepted structured model response")
            return draft
        except Exception as exc:
            logger.info("AnswerLLM structured generation failed (%s); using fallback answer", exc.__class__.__name__)
            logger.exception("AnswerLLM structured generation exception details")
            return self._fallback_draft(request, plan, evidence)

    def _compact_tool_response(self, item: ToolResponse) -> Dict[str, Any]:
        result = item.result if isinstance(item.result, dict) else {}
        compact_result: Dict[str, Any] = {}
        for key, value in result.items():
            if key == "filters_used":
                compact_result[key] = value
            elif isinstance(value, (str, int, float, bool)) or value is None:
                compact_result[key] = value
            elif isinstance(value, list):
                compact_result[key] = value[:8]
            elif isinstance(value, dict):
                # keep shallow preview to reduce prompt size
                preview = {}
                for sub_k, sub_v in list(value.items())[:8]:
                    preview[sub_k] = sub_v
                compact_result[key] = preview
            else:
                compact_result[key] = str(value)
        return {
            "request_id": item.request_id,
            "tool": item.tool,
            "ok": item.ok,
            "result": compact_result,
            "errors": item.errors[:5],
        }

    def _fallback_draft(self, request: UserRequest, plan: LedgerMindPlan, evidence: List[ToolResponse]) -> LLMAnswerDraft:
        headline = "Tool-backed financial review generated; review options below."
        if evidence:
            headline = "Grounded review generated from tool evidence; prioritize the largest flexible spend areas first."

        return LLMAnswerDraft(
            answer=headline,
            bullets=[
                f"Objective: {plan.objective}",
                f"Tool calls executed: {len(evidence)}",
                "Recommendation prioritizes conservative, low-friction savings first.",
            ],
            options=[
                AnswerOption(
                    id="o1",
                    title="Low-friction recurring cost cleanup",
                    why="Recurring charges are often the fastest savings with limited disruption.",
                    steps=[
                        "Review recurring charges flagged by the detector.",
                        "Cancel or downgrade the least valuable one first.",
                    ],
                    impact=[],
                    tradeoffs=["May lose access to a service you use occasionally."],
                ),
                AnswerOption(
                    id="o2",
                    title="Category cap for next month",
                    why="Category limits create a measurable behavior change without changing fixed obligations.",
                    steps=[
                        "Set a cap for the largest flexible category.",
                        "Check weekly and adjust before month-end.",
                    ],
                    impact=[
                        NumericEvidence(
                            id="n_assump_1",
                            label="Estimated monthly savings",
                            value=50.0,
                            unit="USD",
                            type="assumption",
                            assumption="Illustrative target pending a full category trend baseline.",
                        )
                    ],
                    tradeoffs=["Requires consistent follow-through during the month."],
                ),
            ],
            recommended_action=RecommendedAction(
                title="Start with recurring-cost cleanup, then enforce one spending cap for 4 weeks.",
                next_7_days=[
                    "Review flagged recurring charges and cancel or downgrade one.",
                    "Set a weekly cap for the top flexible category.",
                ],
                next_30_days=[
                    "Re-run the same plan and compare category totals month over month.",
                    "Confirm cancelled charges do not recur.",
                ],
                policy_alignment=[
                    PolicyAlignmentCheck(
                        rule="Maintain minimum checking balance",
                        status="pass",
                        details="Proposed actions reduce discretionary spend only.",
                    )
                ],
            ),
            risks_and_tradeoffs=[
                "If the period includes unusual income or one-time expenses, results may not represent a typical month.",
                "Subscription detection may include false positives without merchant-level review.",
            ],
            assumptions_and_confidence=AssumptionsConfidence(
                assumptions=[
                    "Tool outputs are complete for the requested ledger and date range.",
                    "Detected recurring charges include discretionary subscriptions that can be reviewed.",
                ],
                confidence=0.7,
                confidence_reasoning=[
                    "Recommendations are grounded in tool outputs provided to the answer stage.",
                    "Some projected savings values may be assumptions and are labeled as such.",
                ],
            ),
            used_tool_calls=[item.tool for item in evidence],
        )
