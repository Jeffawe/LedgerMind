from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import json
import logging
import sys
from dotenv import load_dotenv

from domain.schemas import TransactionQuery
from infrastructure.get_transactions import get_transactions

load_dotenv()

from infrastructure.ledger_providers.actual_provider import ActualProviderError, ActualLedgerProvider


def _json_default(obj):
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    runner = ActualLedgerProvider()
    # month = sys.argv[1] if len(sys.argv) > 1 else "2026-02"
    try:
        # payload = runner.fetch_budget_month(month)
        # payload = runner.fetch_transactions(start="2026-02-01", end="2026-02-27")
        transaction_query = TransactionQuery(
            date_range={"start": "2026-01-01", "end": "2026-01-31"},
            currency="USD",
        )
        payload =  get_transactions.get_transactions(transaction_query)
    except ActualProviderError as exc:
        print(f"[actual-provider-smoke] error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
