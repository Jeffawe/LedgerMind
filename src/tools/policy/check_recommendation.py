from __future__ import annotations

from typing import Any

from domain.schemas import ToolRequest, ToolResponse
from infrastructure.policy_profile.profile import PolicyProfileStore
from tools.base import Tool, ToolSpec
from tools.registry import register_tool


@register_tool
class PolicyCheckRecommendationTool(Tool):
    name = "policy.check_recommendation"
    description = "Check whether a proposed recommendation aligns with the active policy profile and return pass/warn/fail signals."

    def __init__(self) -> None:
        self._profiles = PolicyProfileStore()

    def run(self, request: ToolRequest) -> ToolResponse:
        args = request.args if isinstance(request.args, dict) else {}
        recommendation = args.get("recommendation")
        rec_text = recommendation if isinstance(recommendation, str) else str(recommendation or "")
        rec_lower = rec_text.lower()

        profile = self._profiles.fetch_policy_profile(request.context.policy_profile)
        checks: list[dict[str, str]] = []

        checks.append(
            {
                "rule": "Provide a concrete recommendation",
                "status": "fail" if not rec_text.strip() else "pass",
                "details": "Recommendation text is required." if not rec_text.strip() else "Recommendation provided.",
            }
        )

        high_risk_keywords = ("margin", "options", "leverage", "crypto", "day trade")
        mentions_high_risk = any(k in rec_lower for k in high_risk_keywords)
        conservative = str(profile.get("risk_tolerance", "")).lower() == "conservative"
        checks.append(
            {
                "rule": "Respect risk tolerance",
                "status": "warning" if conservative and mentions_high_risk else "pass",
                "details": (
                    "Recommendation mentions higher-risk actions while profile is conservative."
                    if conservative and mentions_high_risk
                    else "No obvious risk-tolerance conflict detected."
                ),
            }
        )

        liquidity_keywords = ("emergency fund", "cash buffer", "liquidity", "savings")
        checks.append(
            {
                "rule": "Protect liquidity before optimization",
                "status": "pass" if any(k in rec_lower for k in liquidity_keywords) else "warning",
                "details": (
                    "Recommendation references liquidity/cash buffer protection."
                    if any(k in rec_lower for k in liquidity_keywords)
                    else "Recommendation does not explicitly mention liquidity protection."
                ),
            }
        )

        if "save" in rec_lower or "reduce" in rec_lower:
            checks.append(
                {
                    "rule": "Label estimated savings as assumptions",
                    "status": "pass" if "assumption" in rec_lower or "estimate" in rec_lower else "warning",
                    "details": (
                        "Savings/impact appears labeled as estimate/assumption."
                        if ("assumption" in rec_lower or "estimate" in rec_lower)
                        else "Potential savings claims should be labeled as estimates."
                    ),
                }
            )

        statuses = [c["status"] for c in checks]
        overall = "fail" if "fail" in statuses else ("warning" if "warning" in statuses else "pass")
        result: dict[str, Any] = {
            "overall_status": overall,
            "checks": checks,
            "policy_profile": profile,
        }
        return ToolResponse(request_id=request.request_id, tool=self.name, result=result, context=request.context)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            args_schema={
                "type": "object",
                "properties": {
                    "recommendation": {
                        "type": ["string", "object"],
                        "description": "Proposed recommendation text (or structured object) to validate against policy rules.",
                    }
                },
                "required": ["recommendation"],
            },
        )

