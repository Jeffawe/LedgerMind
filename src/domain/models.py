from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


class TransactionType(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


@dataclass
class Money:
    amount: Decimal
    currency: str = "USD"


@dataclass
class Transaction:
    id: str
    posted_on: date
    description: str
    category: str
    value: Money
    txn_type: TransactionType = TransactionType.DEBIT
    account_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyProfile:
    risk_tolerance: str = "conservative"
    budgeting_style: str = "zero-based"
    notes: str = ""
