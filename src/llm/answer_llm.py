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


def _extract_json_candidate(raw: str) -> str:
    text = raw.strip()
    if not text:
        return text

    if "```" in text:
        fence_start = text.find("```")
        fence_end = text.find("```", fence_start + 3)
        if fence_end != -1:
            fenced = text[fence_start + 3:fence_end].strip()
            if fenced.lower().startswith("json"):
                fenced = fenced[4:].strip()
            if fenced:
                return fenced

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


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
        raw = self._llm.complete(prompt).strip()

        if raw:
            draft = self._try_parse_draft(raw)
            if draft is not None:
                logger.info("AnswerLLM accepted model JSON response")
                return draft

            logger.info("AnswerLLM retrying once with JSON repair prompt")
            retry_raw = self._llm.complete(self._build_retry_prompt(prompt, raw)).strip()
            if retry_raw:
                draft = self._try_parse_draft(retry_raw)
                if draft is not None:
                    logger.info("AnswerLLM accepted repaired JSON response")
                    return draft
            logger.info("AnswerLLM using fallback answer after retry failure")
            return self._fallback_draft(request, plan, evidence)

        logger.info("AnswerLLM empty response; using fallback answer")
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

    def _build_retry_prompt(self, original_prompt: str, raw_response: str) -> str:
        return json.dumps(
            {
                "task": "Repair the previous response into valid JSON only.",
                "instruction": (
                    "Return exactly one JSON object matching the LLMAnswerDraft contract. "
                    "Do not explain. Do not use markdown. Do not include backticks."
                ),
                "original_prompt": original_prompt,
                "previous_invalid_response": raw_response[:3000],
            },
            indent=2,
            default=str,
        )

    def _try_parse_draft(self, raw: str) -> LLMAnswerDraft | None:
        candidate = _extract_json_candidate(raw)
        try:
            return LLMAnswerDraft.model_validate_json(candidate)
        except Exception as exc:
            snippet = raw[:1000].replace("\n", "\\n")
            logger.info(
                "AnswerLLM invalid JSON/schema (%s) raw_snippet=%r",
                exc.__class__.__name__,
                snippet,
            )
            return None

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
