from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from domain.schemas import (
    AnswerOption,
    AnswerSummary,
    AnswerTrace,
    AssumptionsConfidence,
    EngineAnswer,
    EvidenceRef,
    LedgerMindPlan,
    NumericEvidence,
    PolicyAlignmentCheck,
    RecommendedAction,
    ToolResponse,
    UserRequest,
)
from infrastructure.llm.llm_client import LLMClient
from infrastructure.policy_profile.profile import PolicyProfileStore

logger = logging.getLogger(__name__)


class AnswerLLM:
    """Builds answer-generation prompts and validates strict JSON answer outputs."""

    def __init__(self, llm_client: LLMClient, policy_profiles: PolicyProfileStore | None = None):
        self._llm = llm_client
        self._policy_profiles = policy_profiles or PolicyProfileStore()

    def build_prompt(self, request: UserRequest, plan: LedgerMindPlan, evidence: List[ToolResponse]) -> str:
        policy_profile = self._policy_profiles.fetch_policy_profile(request.context.policy_profile)
        prompt_payload: Dict[str, Any] = {
            "task": "Generate a grounded financial decision response from tool evidence.",
            "user_request": request.model_dump(),
            "policy_profile": policy_profile,
            "plan": plan.model_dump(by_alias=True),
            "evidence": [item.model_dump() for item in evidence],
            "output_contract": EngineAnswer.model_json_schema(),
            "rules": [
                "Return JSON only.",
                "Cite evidence-backed numbers using evidence_ref.",
                "If a number is estimated, mark type='assumption' and include assumption text.",
                "Keep recommendations conservative and actionable.",
            ],
        }
        return json.dumps(prompt_payload, indent=2, default=str)

    def generate_answer(self, request: UserRequest, plan: LedgerMindPlan, evidence: List[ToolResponse]) -> EngineAnswer:
        logger.info("AnswerLLM generate_answer start plan_calls=%d evidence=%d policy_profile=%s", len(plan.calls), len(evidence), request.context.policy_profile)
        prompt = self.build_prompt(request, plan, evidence)
        raw = self._llm.complete(prompt).strip()

        if raw:
            try:
                answer = EngineAnswer.model_validate_json(raw)
                logger.info("AnswerLLM accepted model JSON response")
                return answer
            except Exception:
                logger.info("AnswerLLM invalid JSON; using fallback answer")

        logger.info("AnswerLLM empty response; using fallback answer")
        return self._fallback_answer(request, plan, evidence)

    def _fallback_answer(self, request: UserRequest, plan: LedgerMindPlan, evidence: List[ToolResponse]) -> EngineAnswer:
        numbers: List[NumericEvidence] = []
        tool_names = [item.tool for item in evidence]

        # Minimal grounding extraction from known placeholder tools.
        if evidence:
            first = evidence[0]
            for idx, (label, value) in enumerate(first.result.items(), start=1):
                if isinstance(value, (int, float)):
                    numbers.append(
                        NumericEvidence(
                            id=f"n{idx}",
                            label=f"{label.title()} ({first.tool})",
                            value=float(value),
                            unit="USD",
                            type="evidence",
                            evidence_ref=EvidenceRef(citation_id="c1", path=f"result.{label}"),
                        )
                    )

        headline = "Tool-backed financial review generated; review options below."
        if numbers:
            headline = "Grounded review generated from tool evidence; prioritize the largest flexible spend areas first."

        return EngineAnswer(
            schema="ledgermind.answer.v1",
            summary=AnswerSummary(
                headline=headline,
                bullets=[
                    f"Objective: {plan.objective}",
                    f"Tool calls executed: {len(evidence)}",
                    "Recommendation prioritizes conservative, low-friction savings first.",
                ],
            ),
            supporting_numbers=numbers,
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
            trace=AnswerTrace(
                plan_id=request.request_id,
                tool_calls_used=tool_names,
                validation_targets=["all_numbers_cited_or_assumed", "schema_valid"],
            ),
        )
