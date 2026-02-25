from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from domain.schemas import ToolArgs, ToolRequest, ToolResponse
from tools._transactions_support import fetch_transaction_rows
from tools.base import Tool, ToolSpec
from tools.registry import register_tool


@register_tool
class Cashflow30dForecastTool(Tool):
    name = "forecast.cashflow_30d"
    description = "Project net cashflow over the next 30 days using recent daily income/spend patterns."

    def run(self, request: ToolRequest) -> ToolResponse:
        rows, filters = fetch_transaction_rows(request, default_days=90)
        daily_net: dict[str, float] = defaultdict(float)
        debit_total = 0.0
        credit_total = 0.0
        for row in rows:
            amount = float(row.get("amount") or 0.0)
            day = str(row.get("posted_on"))
            if row.get("txn_type") == "credit":
                daily_net[day] += amount
                credit_total += amount
            else:
                daily_net[day] -= amount
                debit_total += amount

        date_range = filters.get("date_range", {})
        try:
            start = date.fromisoformat(str(date_range.get("start")))
            end = date.fromisoformat(str(date_range.get("end")))
            days = max((end - start).days + 1, 1)
        except Exception:
            days = 90

        avg_daily_net = sum(daily_net.values()) / days
        avg_daily_spend = debit_total / days
        avg_daily_income = credit_total / days

        projected_net_30d = round(avg_daily_net * 30, 2)
        projected_spend_30d = round(avg_daily_spend * 30, 2)
        projected_income_30d = round(avg_daily_income * 30, 2)
        start_forecast = date.today() + timedelta(days=1)
        end_forecast = start_forecast + timedelta(days=29)

        result: dict[str, Any] = {
            "lookback_days": days,
            "lookback_transaction_count": len(rows),
            "avg_daily_net": round(avg_daily_net, 2),
            "avg_daily_spend": round(avg_daily_spend, 2),
            "avg_daily_income": round(avg_daily_income, 2),
            "projected_30d": {
                "start": start_forecast.isoformat(),
                "end": end_forecast.isoformat(),
                "net_cashflow": projected_net_30d,
                "spend": projected_spend_30d,
                "income": projected_income_30d,
            },
            "method": "simple trailing average over lookback window (default 90 days)",
            "filters_used": filters,
        }
        return ToolResponse(request_id=request.request_id, tool=self.name, result=result, context=request.context)

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, args_schema=ToolArgs.model_json_schema())
