from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from domain.schemas import ToolArgs, ToolRequest, ToolResponse
from tools._transactions_support import fetch_transaction_rows
from tools.base import Tool, ToolSpec
from tools.registry import register_tool


@register_tool
class DetectAnomaliesTool(Tool):
    name = "detect.anomalies"
    description = "Flag unusually large transactions compared with the user's recent history by category."

    def run(self, request: ToolRequest) -> ToolResponse:
        rows, filters = fetch_transaction_rows(request, default_days=120)
        debit_rows = [r for r in rows if r.get("txn_type") != "credit"]

        by_category: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for row in debit_rows:
            by_category[str(row.get("category") or "uncategorized")].append(
                (str(row.get("id") or ""), float(row.get("amount") or 0))
            )

        anomalies: list[dict[str, Any]] = []
        for row in debit_rows:
            category = str(row.get("category") or "uncategorized")
            amount = float(row.get("amount") or 0)
            history = by_category.get(category, [])
            peers = [peer_amount for peer_id, peer_amount in history if peer_id != str(row.get("id") or "")]
            if len(peers) < 3:
                continue
            avg = mean(peers)
            threshold = max(avg * 2.0, avg + 50.0)
            if amount < threshold:
                continue
            anomalies.append(
                {
                    "transaction_id": row.get("id"),
                    "posted_on": row.get("posted_on"),
                    "description": row.get("description"),
                    "category": category,
                    "amount": round(amount, 2),
                    "category_avg_amount": round(avg, 2),
                    "threshold": round(threshold, 2),
                    "reason": "amount exceeds category baseline",
                }
            )

        anomalies.sort(key=lambda x: x["amount"], reverse=True)
        return ToolResponse(
            request_id=request.request_id,
            tool=self.name,
            result={
                "anomalies": anomalies[:20],
                "transaction_count": len(rows),
                "analyzed_debits": len(debit_rows),
                "filters_used": filters,
            },
            context=request.context,
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, args_schema=ToolArgs.model_json_schema())
