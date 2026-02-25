from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from domain.models import Money, Transaction, TransactionType
from domain.actual_schemas import ActualBudgetMonth
from infrastructure.ledger_providers.provider import Provider
from infrastructure.get_transactions import GetTransactions, get_transactions


class _FakeProvider(Provider):
    def __init__(self, name: str, transactions: list[Transaction]):
        self.name = name
        self._transactions = transactions

    def fetch_budget_month(self, month: str) -> ActualBudgetMonth:
        raise NotImplementedError

    def fetch_transactions(self, _filter):
        return list(self._transactions)


class GetTransactionsSingletonTests(unittest.TestCase):
    def _txn(self, *, id: str, posted_on: date, desc: str, category: str, amount: str, account_id: str, txn_type: TransactionType = TransactionType.DEBIT) -> Transaction:
        return Transaction(
            id=id,
            posted_on=posted_on,
            description=desc,
            category=category,
            value=Money(amount=Decimal(amount), currency="USD"),
            txn_type=txn_type,
            account_id=account_id,
        )

    def test_module_singleton_exists(self) -> None:
        self.assertIsInstance(get_transactions, GetTransactions)

    def test_fetches_from_all_registered_providers_by_default(self) -> None:
        p1 = _FakeProvider("p1", [self._txn(id="t1", posted_on=date(2026, 1, 5), desc="Trader Joe's", category="Groceries", amount="12.50", account_id="checking")])
        p2 = _FakeProvider("p2", [self._txn(id="t2", posted_on=date(2026, 1, 6), desc="Netflix", category="Subscriptions", amount="15.99", account_id="checking")])
        svc = GetTransactions(providers=[p1, p2])

        rows = svc.get_transactions(
            {"date_range": {"start": "2026-01-01", "end": "2026-01-31"}}
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual({r["provider"] for r in rows}, {"p1", "p2"})

    def test_filters_by_source_and_transaction_fields(self) -> None:
        p1 = _FakeProvider("checking_source", [
            self._txn(id="t1", posted_on=date(2026, 1, 10), desc="Whole Foods", category="Groceries", amount="42.10", account_id="checking"),
            self._txn(id="t2", posted_on=date(2026, 2, 1), desc="Rent", category="Housing", amount="1800.00", account_id="checking"),
        ])
        p2 = _FakeProvider("credit_source", [
            self._txn(id="t3", posted_on=date(2026, 1, 12), desc="Gas", category="Transport", amount="60.00", account_id="credit", txn_type=TransactionType.CREDIT),
        ])
        svc = GetTransactions(providers=[p1, p2])

        rows = svc.get_transactions(
            {
                "source": "checking_source",
                "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
                "categories": ["Groceries"],
                "accounts": ["checking"],
                "min_amount": 20,
                "max_amount": 100,
                "query": "whole",
                "positive": True,
            }
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "t1")
        self.assertEqual(rows[0]["provider"], "checking_source")

    def test_positive_false_returns_credits_only(self) -> None:
        p = _FakeProvider("p", [
            self._txn(id="d1", posted_on=date(2026, 1, 1), desc="Store", category="Groceries", amount="10.00", account_id="checking", txn_type=TransactionType.DEBIT),
            self._txn(id="c1", posted_on=date(2026, 1, 1), desc="Refund", category="Groceries", amount="10.00", account_id="checking", txn_type=TransactionType.CREDIT),
        ])
        svc = GetTransactions(providers=[p])

        rows = svc.get_transactions(
            {
                "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
                "positive": False,
            }
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "c1")

    def test_requires_date_range(self) -> None:
        p = _FakeProvider("p", [])
        svc = GetTransactions(providers=[p])

        with self.assertRaises(ValueError):
            svc.get_transactions({"source": "p"})


if __name__ == "__main__":
    unittest.main()
