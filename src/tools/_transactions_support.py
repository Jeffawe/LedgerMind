from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from domain.schemas import TransactionQuery
from infrastructure.get_transactions import get_transactions


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _extract_request_filters(request: Any) -> dict[str, Any]:
    filters: dict[str, Any] = {}

    raw_filters = getattr(request, "filters", None)
    if raw_filters is None:
        raw_filters = getattr(request, "_filters", None)
    if raw_filters is not None and hasattr(raw_filters, "model_dump"):
        try:
            dumped = raw_filters.model_dump(exclude_none=True)
            if isinstance(dumped, dict):
                filters.update(dumped)
        except Exception:
            pass

    # If canonical filters are already present, treat them as authoritative.
    # Tools may set request.filters at runtime (e.g. month_summary) and args can be stale.
    if filters:
        return filters

    args = request.args if isinstance(getattr(request, "args", None), dict) else {}
    if "date_range" in args and isinstance(args["date_range"], dict):
        filters["date_range"] = args["date_range"]
    if "currency" in args and args["currency"]:
        filters["currency"] = args["currency"]

    nested_filters = args.get("filters")
    if isinstance(nested_filters, dict):
        if isinstance(nested_filters.get("accounts"), list):
            filters["accounts"] = nested_filters["accounts"]
        if nested_filters.get("exclude_transfers") is not None:
            filters["exclude_transfers"] = nested_filters["exclude_transfers"]

    for key in ("source", "providers", "provider_names", "accounts", "categories", "query", "txn_type",
                "positive", "min_amount", "max_amount", "exclude_transfers"):
        if key in args and args[key] is not None:
            filters[key] = args[key]

    return filters


def ensure_date_range(filters: dict[str, Any], default_days: int = 30) -> dict[str, Any]:
    if isinstance(filters.get("date_range"), dict):
        start = _coerce_date(filters["date_range"].get("start"))
        end = _coerce_date(filters["date_range"].get("end"))
        if start and end:
            filters["date_range"] = {"start": start.isoformat(), "end": end.isoformat()}
            return filters

    end = date.today()
    start = end - timedelta(days=default_days - 1)
    filters["date_range"] = {"start": start.isoformat(), "end": end.isoformat()}
    return filters


def set_month_date_range(filters: dict[str, Any], year: int, month_number: int) -> dict[str, Any]:
    start = date(year, month_number, 1)
    end = date(year, month_number, monthrange(year, month_number)[1])
    filters["date_range"] = {"start": start.isoformat(), "end": end.isoformat()}
    return filters


def fetch_transaction_rows(request: Any, default_days: int = 30) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    filters = ensure_date_range(_extract_request_filters(request), default_days=default_days)
    if hasattr(request, "filters"):
        try:
            request.filters = TransactionQuery.model_validate(filters)
        except Exception:
            # Leave request.filters untouched if the caller is not a pydantic ToolRequest
            # or if validation is intentionally deferred.
            pass
    rows = get_transactions.get_transactions(filters)
    return rows, filters
