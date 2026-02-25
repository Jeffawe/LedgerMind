from __future__ import annotations

from calendar import month_name
from collections import Counter
from datetime import date
from typing import Any

from domain.schemas import ToolRequest, ToolResponse, TransactionQuery
from tools._transactions_support import _extract_request_filters, fetch_transaction_rows, set_month_date_range
from tools.base import Tool, ToolSpec
from tools.registry import register_tool


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


@register_tool
class MonthSummaryTool(Tool):
    name = "ledgers.month_summary"
    description = (
        "Summarize monthly spending/income totals and top categories. "
        "Takes `month_number` (1-12) as an argument; optional `year` defaults to current year."
    )

    def run(self, request: ToolRequest) -> ToolResponse:
        args = request.args if isinstance(request.args, dict) else {}
        month_number = _as_int(args.get("month_number") or args.get("month"))
        year = _as_int(args.get("year")) or date.today().year

        if month_number is None or month_number < 1 or month_number > 12:
            return ToolResponse(
                request_id=request.request_id,
                tool=self.name,
                ok=False,
                errors=["month_number must be an integer from 1 to 12"],
                context=request.context,
            )

        filters = _extract_request_filters(request)
        set_month_date_range(filters, year, month_number)
        request.filters = TransactionQuery.model_validate(filters)
        rows, filters = fetch_transaction_rows(request, default_days=31)

        debit_total = round(sum(float(r.get("amount") or 0) for r in rows if r.get("txn_type") != "credit"), 2)
        credit_total = round(sum(float(r.get("amount") or 0) for r in rows if r.get("txn_type") == "credit"), 2)
        net_cashflow = round(credit_total - debit_total, 2)

        by_category = Counter()
        for row in rows:
            if row.get("txn_type") == "credit":
                continue
            by_category[str(row.get("category") or "uncategorized")] += float(row.get("amount") or 0)

        top_categories = [
            {"category": cat, "debit_total": round(total, 2)}
            for cat, total in by_category.most_common(5)
        ]

        result = {
            "year": year,
            "month_number": month_number,
            "month_name": month_name[month_number],
            "transaction_count": len(rows),
            "debit_total": debit_total,
            "credit_total": credit_total,
            "net_cashflow": net_cashflow,
            "top_debit_categories": top_categories,
            "filters_used": filters,
        }
        return ToolResponse(request_id=request.request_id, tool=self.name, result=result, context=request.context)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            args_schema={
                "type": "object",
                "properties": {
                    "month_number": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 12,
                        "description": "Calendar month number to summarize (1=Jan ... 12=Dec).",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Four-digit year for the monthly summary. Defaults to current year.",
                    },
                    "currency": {"type": "string"},
                    "filters": {"type": "object"},
                },
                "required": ["month_number"],
            },
        )
