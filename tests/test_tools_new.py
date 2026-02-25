from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tools  # noqa: F401
from domain.schemas import ToolContext
from tools.registry import registry
from tools._transactions_support import fetch_transaction_rows


def _request(tool_name: str, args: dict | None = None):
    args = args or {}
    date_range = args.get("date_range") if isinstance(args, dict) else None
    filters_payload = {"date_range": date_range or {"start": "2026-01-01", "end": "2026-03-31"}}
    if args.get("currency"):
        filters_payload["currency"] = args["currency"]
    return SimpleNamespace(
        request_id=f"req:{tool_name}",
        tool=tool_name,
        args=args,
        filters=SimpleNamespace(model_dump=lambda exclude_none=True: dict(filters_payload)),
        context=ToolContext(
            user_id="u_123",
            ledger_id="ldg_main",
            timezone="America/New_York",
            policy_profile="default_v1",
        ),
    )


class ToolRegistrationTests(unittest.TestCase):
    def test_requested_tools_are_registered(self) -> None:
        names = {spec.name for spec in registry.list_specs()}
        self.assertIn("ledgers.month_summary", names)
        self.assertIn("ledgers.category_summary", names)
        self.assertIn("detect.recurring_charges", names)
        self.assertIn("policy.check_recommendation", names)
        self.assertIn("detect.anomalies", names)
        self.assertIn("forecast.cashflow_30d", names)

    @patch("tools._transactions_support.get_transactions.get_transactions")
    def test_fetch_transaction_rows_derives_and_persists_filters(self, mock_get_transactions) -> None:
        mock_get_transactions.return_value = []
        req = _request(
            "dummy",
            {
                "date_range": {"start": "2026-01-01", "end": "2026-01-31"},
                "currency": "USD",
                "filters": {"accounts": ["checking"], "exclude_transfers": True},
            },
        )
        req.filters = None
        _, filters_used = fetch_transaction_rows(req, default_days=30)
        self.assertIsNotNone(req.filters)
        dumped = req.filters.model_dump()
        self.assertEqual(dumped["date_range"]["start"].isoformat(), "2026-01-01")
        self.assertEqual(dumped["currency"], "USD")
        self.assertEqual(dumped["accounts"], ["checking"])
        self.assertEqual(filters_used["date_range"]["start"], "2026-01-01")


class TransactionBackedToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "id": "t1",
                "provider": "actual",
                "posted_on": "2026-01-03",
                "description": "Netflix 1234",
                "category": "Subscriptions",
                "amount": 15.99,
                "currency": "USD",
                "txn_type": "debit",
                "account_id": "checking",
                "metadata": {},
            },
            {
                "id": "t2",
                "provider": "actual",
                "posted_on": "2026-02-03",
                "description": "Netflix 5678",
                "category": "Subscriptions",
                "amount": 15.99,
                "currency": "USD",
                "txn_type": "debit",
                "account_id": "checking",
                "metadata": {},
            },
            {
                "id": "t3",
                "provider": "actual",
                "posted_on": "2026-03-03",
                "description": "Netflix 9999",
                "category": "Subscriptions",
                "amount": 16.49,
                "currency": "USD",
                "txn_type": "debit",
                "account_id": "checking",
                "metadata": {},
            },
            {
                "id": "t4",
                "provider": "actual",
                "posted_on": "2026-03-05",
                "description": "Trader Joe's",
                "category": "Groceries",
                "amount": 52.10,
                "currency": "USD",
                "txn_type": "debit",
                "account_id": "checking",
                "metadata": {},
            },
            {
                "id": "t5",
                "provider": "actual",
                "posted_on": "2026-03-10",
                "description": "Whole Foods",
                "category": "Groceries",
                "amount": 48.25,
                "currency": "USD",
                "txn_type": "debit",
                "account_id": "checking",
                "metadata": {},
            },
            {
                "id": "t6",
                "provider": "actual",
                "posted_on": "2026-03-17",
                "description": "Whole Foods",
                "category": "Groceries",
                "amount": 51.00,
                "currency": "USD",
                "txn_type": "debit",
                "account_id": "checking",
                "metadata": {},
            },
            {
                "id": "t7",
                "provider": "actual",
                "posted_on": "2026-03-24",
                "description": "Whole Foods",
                "category": "Groceries",
                "amount": 210.00,
                "currency": "USD",
                "txn_type": "debit",
                "account_id": "checking",
                "metadata": {},
            },
            {
                "id": "t8",
                "provider": "actual",
                "posted_on": "2026-03-28",
                "description": "Payroll",
                "category": "Income",
                "amount": 2500.00,
                "currency": "USD",
                "txn_type": "credit",
                "account_id": "checking",
                "metadata": {},
            },
        ]

    @patch("tools._transactions_support.get_transactions.get_transactions")
    def test_ledgers_category_summary(self, mock_get_transactions) -> None:
        mock_get_transactions.return_value = self.rows
        tool = registry.get_tool("ledgers.category_summary")
        req = _request(
            "ledgers.category_summary",
            {"date_range": {"start": "2026-03-01", "end": "2026-03-31"}, "currency": "USD"},
        )

        res = tool.run(req)

        self.assertTrue(res.ok)
        self.assertEqual(res.tool, "ledgers.category_summary")
        self.assertGreaterEqual(res.result["category_count"], 2)
        self.assertIn("filters_used", res.result)
        self.assertAlmostEqual(res.result["total_credit"], 2500.00, places=2)

    @patch("tools._transactions_support.get_transactions.get_transactions")
    def test_ledgers_month_summary_uses_month_number_arg(self, mock_get_transactions) -> None:
        mock_get_transactions.return_value = self.rows
        tool = registry.get_tool("ledgers.month_summary")
        req = _request("ledgers.month_summary", {"month_number": 3, "year": 2026, "currency": "USD"})

        res = tool.run(req)

        self.assertTrue(res.ok)
        self.assertEqual(res.result["month_number"], 3)
        self.assertEqual(res.result["year"], 2026)
        self.assertEqual(res.result["filters_used"]["date_range"]["start"], "2026-03-01")
        self.assertEqual(res.result["filters_used"]["date_range"]["end"], "2026-03-31")
        self.assertIn("top_debit_categories", res.result)

    @patch("tools._transactions_support.get_transactions.get_transactions")
    def test_detect_recurring_charges_finds_netflix_pattern(self, mock_get_transactions) -> None:
        mock_get_transactions.return_value = self.rows
        tool = registry.get_tool("detect.recurring_charges")
        req = _request("detect.recurring_charges", {"date_range": {"start": "2026-01-01", "end": "2026-03-31"}})

        res = tool.run(req)

        self.assertTrue(res.ok)
        detected = res.result["detected"]
        self.assertTrue(any("netflix" in item["merchant"] for item in detected))

    @patch("tools._transactions_support.get_transactions.get_transactions")
    def test_detect_anomalies_flags_large_grocery_spend(self, mock_get_transactions) -> None:
        mock_get_transactions.return_value = self.rows
        tool = registry.get_tool("detect.anomalies")
        req = _request("detect.anomalies", {"date_range": {"start": "2026-01-01", "end": "2026-03-31"}})

        res = tool.run(req)

        self.assertTrue(res.ok)
        anomalies = res.result["anomalies"]
        self.assertTrue(any(a["transaction_id"] == "t7" for a in anomalies))

    @patch("tools._transactions_support.get_transactions.get_transactions")
    def test_forecast_cashflow_30d_returns_projection(self, mock_get_transactions) -> None:
        mock_get_transactions.return_value = self.rows
        tool = registry.get_tool("forecast.cashflow_30d")
        req = _request("forecast.cashflow_30d", {"date_range": {"start": "2026-01-01", "end": "2026-03-31"}})

        res = tool.run(req)

        self.assertTrue(res.ok)
        self.assertIn("projected_30d", res.result)
        self.assertIn("net_cashflow", res.result["projected_30d"])
        self.assertEqual(res.result["lookback_transaction_count"], len(self.rows))


class PolicyToolTests(unittest.TestCase):
    def test_policy_check_recommendation_warns_on_risk_and_missing_estimate_label(self) -> None:
        tool = registry.get_tool("policy.check_recommendation")
        req = _request(
            "policy.check_recommendation",
            {"recommendation": "Use crypto to save money fast and reduce expenses by $500/month."},
        )

        res = tool.run(req)

        self.assertTrue(res.ok)
        self.assertIn(res.result["overall_status"], {"warning", "fail"})
        statuses = {c["status"] for c in res.result["checks"]}
        self.assertIn("warning", statuses)


if __name__ == "__main__":
    unittest.main()
