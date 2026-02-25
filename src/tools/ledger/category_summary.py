from __future__ import annotations

from collections import defaultdict
from typing import Any

from domain.schemas import ToolArgs, ToolRequest, ToolResponse
from tools._transactions_support import fetch_transaction_rows
from tools.base import Tool, ToolSpec
from tools.registry import register_tool


def _build_category_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "category": "uncategorized",
            "txn_count": 0,
            "debit_total": 0.0,
            "credit_total": 0.0,
            "net_total": 0.0,
        }
    )

    for row in rows:
        category = str(row.get("category") or "uncategorized")
        amount = float(row.get("amount") or 0.0)
        txn_type = str(row.get("txn_type") or "debit")
        entry = groups[category]
        entry["category"] = category
        entry["txn_count"] += 1
        if txn_type == "credit":
            entry["credit_total"] += amount
            entry["net_total"] += amount
        else:
            entry["debit_total"] += amount
            entry["net_total"] -= amount

    categories = sorted(groups.values(), key=lambda x: (x["debit_total"] + x["credit_total"]), reverse=True)
    return {
        "categories": categories,
        "category_count": len(categories),
        "total_debit": round(sum(c["debit_total"] for c in categories), 2),
        "total_credit": round(sum(c["credit_total"] for c in categories), 2),
        "net_total": round(sum(c["net_total"] for c in categories), 2),
    }


class _CategorySummaryBase(Tool):
    description = "Summarize spend/income totals grouped by category for the filtered transaction date range."

    def run(self, request: ToolRequest) -> ToolResponse:
        rows, filters = fetch_transaction_rows(request, default_days=30)
        result = _build_category_summary(rows)
        result["filters_used"] = filters
        result["transaction_count"] = len(rows)
        return ToolResponse(
            request_id=request.request_id,
            tool=self.name,
            result=result,
            context=request.context,
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, args_schema=ToolArgs.model_json_schema())


@register_tool
class CategorySummaryToolLegacy(_CategorySummaryBase):
    name = "ledger.category_summary"


@register_tool
class CategorySummaryTool(_CategorySummaryBase):
    name = "ledgers.category_summary"
