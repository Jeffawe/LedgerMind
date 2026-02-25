#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from typing import Any

try:
    from ._actualpy_common import as_int, emit_json, log, normalize_query_result, open_actual_client
except ImportError:
    from _actualpy_common import as_int, emit_json, log, normalize_query_result, open_actual_client


def parse_args() -> str:
    if len(sys.argv) != 2:
        raise ValueError("Usage: python scripts/actual/get_budget_month.py YYYY-MM")
    month = sys.argv[1]
    if len(month) != 7 or month[4] != "-":
        raise ValueError("Usage: python scripts/actual/get_budget_month.py YYYY-MM")
    return month


def month_to_date(month: str) -> date:
    year_str, month_str = month.split("-", 1)
    return date(int(year_str), int(month_str), 1)


def _minor_from_decimalish(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return int((value * 100).to_integral_value())
    try:
        return int(value)
    except Exception:
        return 0


def _getattr_many(obj: Any, *names: str) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def fetch_budget_month(month: str) -> dict[str, Any]:
    from actual.queries import get_budgets  # type: ignore

    with open_actual_client() as actual:
        groups_map: dict[str, dict[str, Any]] = {}
        total_budgeted = 0
        total_spent = 0
        total_balance = 0
        total_income = 0

        target_month = month_to_date(month)
        log(f"[actual-py] get_budgets month={target_month}")
        budgets = normalize_query_result(get_budgets(actual.session, month=target_month))

        for budget in budgets:
            category_obj = _getattr_many(budget, "category")
            if category_obj is None:
                continue
            group_obj = _getattr_many(category_obj, "group")

            group_id = str(_getattr_many(group_obj, "id") or "ungrouped")
            group_name = str(_getattr_many(group_obj, "name") or "Ungrouped")
            is_income = bool(_getattr_many(category_obj, "is_income", "isIncome") or False)
            hidden = bool(_getattr_many(category_obj, "hidden") or False)

            budgeted_minor = as_int(_getattr_many(budget, "amount"))
            spent_minor = _minor_from_decimalish(_getattr_many(budget, "balance"))
            balance_minor = budgeted_minor + spent_minor
            received_minor = -spent_minor if is_income else None

            category = {
                "id": str(_getattr_many(category_obj, "id") or _getattr_many(budget, "category_id") or ""),
                "name": str(_getattr_many(category_obj, "name") or ""),
                "is_income": is_income,
                "hidden": hidden,
                "group_id": group_id,
                "carryover": _getattr_many(budget, "carryover"),
                "budgeted": budgeted_minor,
                "spent": spent_minor,
                "balance": balance_minor,
                "received": received_minor,
            }

            group = groups_map.get(group_id)
            if group is None:
                group = {
                    "id": group_id,
                    "name": group_name,
                    "is_income": is_income,
                    "hidden": hidden,
                    "categories": [],
                    "budgeted": 0,
                    "spent": 0,
                    "balance": 0,
                    "received": 0,
                }
                groups_map[group_id] = group

            group["categories"].append(category)
            if category["budgeted"] is not None:
                group["budgeted"] += category["budgeted"]
                total_budgeted += category["budgeted"]
            if category["spent"] is not None:
                group["spent"] += category["spent"]
                total_spent += category["spent"]
            if category["balance"] is not None:
                group["balance"] += category["balance"]
                total_balance += category["balance"]
            if category["received"] is not None:
                group["received"] += category["received"]
                total_income += category["received"]

        # NOTE: actualpy's query helpers expose category/group history easily. These
        # top-level monthly summary values are set to 0 unless you add a richer report query.
        return {
            "month": month,
            "incomeAvailable": 0,
            "lastMonthOverspent": 0,
            "forNextMonth": 0,
            "totalBudgeted": total_budgeted,
            "toBudget": 0,
            "fromLastMonth": 0,
            "totalIncome": total_income,
            "totalSpent": total_spent,
            "totalBalance": total_balance,
            "categoryGroups": list(groups_map.values()),
        }


def main() -> int:
    try:
        month = parse_args()
        emit_json(fetch_budget_month(month))
        return 0
    except Exception as exc:
        print(f"[actual-py] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
