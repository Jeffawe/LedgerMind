from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from domain.actual_schemas import ActualBudgetMonth
from domain.models import Money, Transaction, TransactionType
from domain.schemas import TransactionQuery
from infrastructure.ledger_providers.provider import Provider

logger = logging.getLogger(__name__)


class ActualProviderError(RuntimeError):
    pass


class ActualLedgerProvider(Provider):
    """Adapter for pulling data from Actual via Python bridge helpers."""

    name = "actual"

    def __init__(
        self,
        timeout_seconds: float | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self._repo_root = repo_root
        self._timeout_seconds = timeout_seconds or float(os.getenv("ACTUAL_SCRIPT_TIMEOUT_SECONDS", "120"))

    def fetch_budget_month(self, month: str) -> ActualBudgetMonth:
        logger.info(
            "Actual provider calling budget-month bridge (python) month=%s",
            month,
        )
        try:
            payload = self._fetch_budget_month_via_python(month)
        except Exception as exc:
            raise ActualProviderError(f"Actual python bridge failed for budget month {month}: {exc}") from exc

        try:
            budget_month = ActualBudgetMonth.model_validate(payload)
        except Exception as exc:
            raise ActualProviderError(f"Actual bridge payload did not match ActualBudgetMonth schema: {exc}") from exc

        logger.info("Actual provider received budget month payload type=%s", type(budget_month).__name__)
        return budget_month

    def fetch_transactions(self, _filter: TransactionQuery) -> list[Transaction]:
        date_range = _filter.date_range
        start_str = date_range.start.isoformat()
        end_str = date_range.end.isoformat()
        logger.info(
            "Actual provider calling transactions bridge (python) start=%s end=%s",
            start_str,
            end_str,
        )
        try:
            rows = self._fetch_transactions_via_python(date_range.start, date_range.end)
        except Exception as exc:
            raise ActualProviderError(
                f"Actual python bridge failed for transactions {start_str}..{end_str}: {exc}"
            ) from exc

        if not isinstance(rows, list):
            raise ActualProviderError(f"Expected transaction rows list from bridge, got {type(rows).__name__}")

        transactions = [self._normalize_transaction_row(row) for row in rows if isinstance(row, dict)]
        logger.info("Actual provider normalized transactions count=%d", len(transactions))
        return transactions

    def _import_actualpy_bridge(self) -> tuple[Any, Any]:
        if str(self._repo_root) not in sys.path:
            sys.path.insert(0, str(self._repo_root))
        try:
            from scripts.actual.get_budget_month import fetch_budget_month
            from scripts.actual.get_transactions import fetch_transactions
        except Exception as exc:
            raise ActualProviderError(f"Unable to import Python Actual bridge modules: {exc}") from exc
        return fetch_budget_month, fetch_transactions

    def _fetch_budget_month_via_python(self, month: str) -> dict[str, Any]:
        fetch_budget_month, _ = self._import_actualpy_bridge()
        payload = fetch_budget_month(month)
        if not isinstance(payload, dict):
            raise ActualProviderError(f"Expected dict budget payload from python bridge, got {type(payload).__name__}")
        return payload

    def _fetch_transactions_via_python(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        _, fetch_transactions = self._import_actualpy_bridge()
        rows = fetch_transactions(start_date, end_date)
        if not isinstance(rows, list):
            raise ActualProviderError(f"Expected list transaction payload from python bridge, got {type(rows).__name__}")
        return rows

    def _normalize_transaction_row(self, row: dict[str, Any]) -> Transaction:
        amount_minor = int(row.get("amount", 0))
        txn_type = TransactionType.CREDIT if amount_minor > 0 else TransactionType.DEBIT
        amount_major = (Decimal(abs(amount_minor)) / Decimal("100")).quantize(Decimal("0.01"))

        raw_synced = self._parse_raw_synced_data(row.get("raw_synced_data"))
        tx_amount = raw_synced.get("transactionAmount") if isinstance(raw_synced, dict) else None
        currency = tx_amount.get("currency", "USD") if isinstance(tx_amount, dict) else "USD"

        description = row.get("imported_payee") or row.get("notes") or row.get("id") or "Unknown"
        posted_on = self._parse_actual_date(row.get("date"))
        account_id = str(row.get("account") or row.get("accountId") or "")
        category_id = row.get("category")

        metadata: dict[str, Any] = {
            "source_provider": self.name,
            "source_transaction_id": row.get("id"),
            "actual_account_id": account_id,
            "actual_category_id": category_id,
            "actual_payee_id": row.get("payee"),
            "imported_id": row.get("imported_id"),
            "imported_payee": row.get("imported_payee"),
            "notes": row.get("notes"),
            "cleared": row.get("cleared"),
            "reconciled": row.get("reconciled"),
            "transfer_id": row.get("transfer_id"),
            "is_parent": row.get("is_parent"),
            "is_child": row.get("is_child"),
            "parent_id": row.get("parent_id"),
            "starting_balance_flag": row.get("starting_balance_flag"),
            "tombstone": row.get("tombstone"),
            "payee_id": row.get("payee"),
            "subtransactions": row.get("subtransactions") or [],
        }
        if raw_synced:
            metadata["raw_synced_data"] = raw_synced

        return Transaction(
            id=str(row.get("id")),
            posted_on=posted_on,
            description=str(description),
            category=str(category_id or "uncategorized"),
            value=Money(amount=amount_major, currency=str(currency)),
            txn_type=txn_type,
            account_id=account_id or None,
            metadata=metadata,
        )

    def _parse_raw_synced_data(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw:
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    def _parse_actual_date(self, raw_date: Any) -> date:
        value = str(raw_date or "").strip()
        if not value:
            raise ActualProviderError("Transaction row missing date")
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        if len(value) == 8 and value.isdigit():
            return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
        raise ActualProviderError(f"Unsupported Actual transaction date format: {value!r}")
