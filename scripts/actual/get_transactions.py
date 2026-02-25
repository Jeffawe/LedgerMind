#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import date
from typing import Any

try:
    from ._actualpy_common import emit_json, log, normalize_query_result, open_actual_client
except ImportError:
    from _actualpy_common import emit_json, log, normalize_query_result, open_actual_client


def parse_args() -> tuple[date, date]:
    if len(sys.argv) != 3:
        raise ValueError("Usage: python scripts/actual/get_transactions.py YYYY-MM-DD YYYY-MM-DD")
    return date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])


def _txn_row(txn: Any) -> dict[str, Any]:
    account_obj = getattr(txn, "account", None)
    account_id = (
        getattr(txn, "account_id", None)
        or getattr(txn, "accountId", None)
        or getattr(account_obj, "id", None)
    )
    category_obj = getattr(txn, "category", None)
    category_id = (
        getattr(txn, "category_id", None)
        or getattr(txn, "categoryId", None)
        or getattr(category_obj, "id", None)
    )
    payee_obj = getattr(txn, "payee", None)
    payee_id = getattr(payee_obj, "id", None) if payee_obj is not None else getattr(txn, "payee_id", None)

    raw_synced_data = getattr(txn, "raw_synced_data", None)
    if raw_synced_data is None:
        raw_synced_data = getattr(txn, "rawSyncedData", None)

    row = {
        "id": getattr(txn, "id", None),
        "date": getattr(txn, "date", None),
        "amount": getattr(txn, "amount", None),
        "notes": getattr(txn, "notes", None),
        "cleared": getattr(txn, "cleared", None),
        "reconciled": getattr(txn, "reconciled", None),
        "transfer_id": getattr(txn, "transfer_id", None),
        "parent_id": getattr(txn, "parent_id", None),
        "starting_balance_flag": getattr(txn, "starting_balance_flag", None),
        "tombstone": getattr(txn, "tombstone", None),
        "imported_id": getattr(txn, "imported_id", None),
        "imported_payee": getattr(txn, "imported_payee", None),
        "raw_synced_data": raw_synced_data,
        "is_parent": bool(getattr(txn, "is_parent", False)),
        "is_child": bool(getattr(txn, "is_child", False)),
        "account": account_id,
        "accountId": account_id,
        "category": category_id,
        "payee": payee_id,
        # Keep shape parity with JS bridge.
        "subtransactions": [],
    }

    # Fallbacks for versions that expose different attribute names.
    if row["imported_payee"] is None:
        row["imported_payee"] = getattr(txn, "payee_name", None) or getattr(payee_obj, "name", None)
    return row


def fetch_transactions(start_date: date, end_date: date) -> list[dict[str, Any]]:
    from actual.queries import get_transactions  # type: ignore

    with open_actual_client() as actual:
        log(f"[actual-py] get_transactions start={start_date} end={end_date}")
        txns = normalize_query_result(
            get_transactions(actual.session, start_date=start_date, end_date=end_date)
        )
        return [_txn_row(txn) for txn in txns]


def main() -> int:
    try:
        start_date, end_date = parse_args()
        emit_json(fetch_transactions(start_date, end_date))
        return 0
    except Exception as exc:
        print(f"[actual-py] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
