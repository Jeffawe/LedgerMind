from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ActualCategory(BaseModel):
    id: str
    name: str
    is_income: bool
    hidden: bool
    group_id: str
    carryover: Optional[bool] = None

    # Expense-style fields
    budgeted: Optional[int] = None
    spent: Optional[int] = None
    balance: Optional[int] = None

    # Income-style field
    received: Optional[int] = None


class ActualCategoryGroup(BaseModel):
    id: str
    name: str
    is_income: bool
    hidden: bool
    categories: list[ActualCategory] = Field(default_factory=list)

    # Expense-style totals
    budgeted: Optional[int] = None
    spent: Optional[int] = None
    balance: Optional[int] = None

    # Income-style total
    received: Optional[int] = None


class ActualBudgetMonth(BaseModel):
    month: str
    incomeAvailable: int
    lastMonthOverspent: int
    forNextMonth: int
    totalBudgeted: int
    toBudget: int
    fromLastMonth: int
    totalIncome: int
    totalSpent: int
    totalBalance: int
    categoryGroups: list[ActualCategoryGroup] = Field(default_factory=list)

