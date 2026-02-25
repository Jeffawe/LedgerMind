from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from domain.actual_schemas import ActualBudgetMonth
from domain.models import Transaction
from domain.schemas import TransactionQuery


class Provider(ABC):
    """Base provider contract for normalized transaction sources."""

    name: str = "provider"

    @abstractmethod
    def fetch_budget_month(self, month: str) -> ActualBudgetMonth:
        raise NotImplementedError()

    @abstractmethod
    def fetch_transactions(self, _filter: TransactionQuery) -> list[Transaction]:
        raise NotImplementedError
