from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from pydantic import ValidationError

from domain.models import Transaction
from domain.schemas import TransactionQuery
from infrastructure.ledger_providers.actual_provider import ActualLedgerProvider
from infrastructure.ledger_providers.provider import Provider

class GetTransactions:
    """
    Aggregates normalized transactions across registered providers.

    Dynamic behavior:
    - Providers can be added/removed at runtime via add_provider/remove_provider
    - If no provider filter is passed, fetches from all registered providers
    - Supports provider-level filtering and transaction-level filtering
    """

    def __init__(self, providers: Iterable[Provider] | None = None) -> None:
        self._providers: dict[str, Provider] = {}
        for provider in providers or [ActualLedgerProvider()]:
            self.add_provider(provider)

    # ---- dynamic provider management ----
    def add_provider(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

    def remove_provider(self, provider_name: str) -> None:
        self._providers.pop(provider_name, None)

    def list_provider_names(self) -> list[str]:
        return sorted(self._providers.keys())

    def get_transactions(
        self,
        filters: TransactionQuery | dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Fetch transactions from all providers (default) or a filtered subset.

        `filters` supports provider/source filters and transaction-level filters, e.g.:
          - source / providers / provider_names
          - date_range
          - accounts
          - categories
          - currency
          - txn_type
          - positive (True -> debits only, False -> credits only)
          - min_amount / max_amount
          - query
        """
        query = self._normalize_filters(filters)
        args = query.model_dump()
        selected = self._select_providers(args)

        rows: list[dict[str, Any]] = []
        for provider in selected:
            txns = provider.fetch_transactions(query)
            for txn in txns:
                if self._transaction_matches(txn, args):
                    rows.append(self._serialize_transaction(txn, provider.name))
        return rows

    def _normalize_filters(self, filters: TransactionQuery | dict[str, Any]) -> TransactionQuery:
        if isinstance(filters, TransactionQuery):
            return filters
        try:
            query = TransactionQuery.model_validate(filters)
        except ValidationError as exc:
            raise ValueError(f"Invalid TransactionQuery: {exc}") from exc
        return query

    # ---- provider filtering ----
    def _select_providers(self, args: dict[str, Any]) -> list[Provider]:
        source = args.get("source")
        requested = args.get("providers") or args.get("provider_names") or ([source] if source else [])
        if not requested:
            return list(self._providers.values())

        requested_set = {str(name) for name in requested}
        return [p for name, p in self._providers.items() if name in requested_set]

    # ---- transaction filtering ----
    def _transaction_matches(self, txn: Transaction, args: dict[str, Any]) -> bool:
        if not self._match_date_range(txn, args.get("date_range")):
            return False

        accounts = {str(a) for a in (args.get("accounts") or [])}
        if accounts and (txn.account_id or "") not in accounts:
            return False

        categories = {str(c).lower() for c in (args.get("categories") or [])}
        if categories and txn.category.lower() not in categories:
            return False

        currency = args.get("currency")
        if currency and txn.value.currency != currency:
            return False

        txn_type = args.get("txn_type")
        if txn_type and txn.txn_type.value != str(txn_type):
            return False

        positive = args.get("positive")
        if positive is True and txn.txn_type != txn.txn_type.DEBIT:
            return False
        if positive is False and txn.txn_type != txn.txn_type.CREDIT:
            return False

        amount = float(txn.value.amount)
        min_amount = args.get("min_amount")
        if min_amount is not None and amount < float(min_amount):
            return False
        max_amount = args.get("max_amount")
        if max_amount is not None and amount > float(max_amount):
            return False

        query = (args.get("query") or "").strip().lower()
        if query and query not in txn.description.lower() and query not in txn.category.lower():
            return False

        return True

    def _match_date_range(self, txn: Transaction, date_range: Any) -> bool:
        if not isinstance(date_range, dict):
            return True
        start = self._parse_date(date_range.get("start"))
        end = self._parse_date(date_range.get("end"))
        if start and txn.posted_on < start:
            return False
        if end and txn.posted_on > end:
            return False
        return True

    def _parse_date(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _serialize_transaction(self, txn: Transaction, provider_name: str) -> dict[str, Any]:
        return {
            "id": txn.id,
            "provider": provider_name,
            "posted_on": txn.posted_on.isoformat(),
            "description": txn.description,
            "category": txn.category,
            "amount": float(txn.value.amount),
            "currency": txn.value.currency,
            "txn_type": txn.txn_type.value,
            "account_id": txn.account_id,
            "metadata": txn.metadata,
        }


# Singleton instance used across the codebase.
get_transactions = GetTransactions()

# rows = get_transactions.get_transactions({
#     "source": "actual",
#     "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
#     "currency": "USD",
#     "positive": True,
# })
