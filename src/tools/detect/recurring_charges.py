from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from statistics import mean
from typing import Any

from domain.schemas import ToolArgs, ToolRequest, ToolResponse
from tools._transactions_support import fetch_transaction_rows
from tools.base import Tool, ToolSpec
from tools.registry import register_tool


def _norm_merchant(text: str) -> str:
    value = (text or "").lower()
    value = re.sub(r"\d+", "", value)
    value = re.sub(r"[^a-z ]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "unknown"


def _parse_posted_on(row: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(row.get("posted_on")))
    except Exception:
        return None


def _detect(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_merchant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("txn_type") == "credit":
            continue
        by_merchant[_norm_merchant(str(row.get("description") or ""))].append(row)

    candidates: list[dict[str, Any]] = []
    for merchant, entries in by_merchant.items():
        parsed = []
        for row in entries:
            posted = _parse_posted_on(row)
            if posted is None:
                continue
            parsed.append((posted, float(row.get("amount") or 0.0), row))
        parsed.sort(key=lambda x: x[0])
        if len(parsed) < 3:
            continue

        deltas = [(parsed[i][0] - parsed[i - 1][0]).days for i in range(1, len(parsed))]
        avg_delta = mean(deltas)
        if not (24 <= avg_delta <= 38):
            continue

        amounts = [p[1] for p in parsed]
        avg_amount = mean(amounts)
        spread = max(amounts) - min(amounts)
        if avg_amount <= 0 or spread > max(3.0, avg_amount * 0.25):
            continue

        next_est = parsed[-1][0].toordinal() + round(avg_delta)
        candidates.append(
            {
                "merchant": merchant,
                "count": len(parsed),
                "avg_amount": round(avg_amount, 2),
                "avg_interval_days": round(avg_delta, 1),
                "amount_spread": round(spread, 2),
                "last_seen": parsed[-1][0].isoformat(),
                "next_expected_on": date.fromordinal(next_est).isoformat(),
                "examples": [p[2]["description"] for p in parsed[-2:]],
            }
        )

    return sorted(candidates, key=lambda x: (x["count"], x["avg_amount"]), reverse=True)


class _RecurringBase(Tool):
    description = "Detect likely recurring charges (subscriptions and repeating bills) from recent debit transactions."

    def run(self, request: ToolRequest) -> ToolResponse:
        rows, filters = fetch_transaction_rows(request, default_days=180)
        result = {
            "detected": _detect(rows),
            "transaction_count": len(rows),
            "filters_used": filters,
        }
        return ToolResponse(request_id=request.request_id, tool=self.name, result=result, context=request.context)

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, args_schema=ToolArgs.model_json_schema())


@register_tool
class RecurringChargesTool(_RecurringBase):
    name = "detect.recurring_charges"


@register_tool
class SubscriptionDetectionToolAlias(_RecurringBase):
    name = "detect.subscriptions"
