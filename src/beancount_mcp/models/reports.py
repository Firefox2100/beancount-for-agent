import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class AccountTotal(BaseModel):
    account: str
    totals: dict[str, str] = Field(description="Per currency. Always positive for what was earned or spent; a refund reduces an expense.")
    previous: dict[str, str] | None = Field(default=None, description="The same for the period before, when compared.")


class PeriodTotal(BaseModel):
    start: dt.date
    end: dt.date
    income: dict[str, str]
    expenses: dict[str, str]
    net: dict[str, str] = Field(description="Income less expenses, per currency. Negative when more was spent than earned.")


class IncomeStatement(BaseModel):
    """What came in and what went out over a period, by account, in the currencies it happened in."""

    ledger: str
    start: dt.date
    end: dt.date
    depth: int = Field(description="Accounts are grouped to this many name segments, such as Expenses:Food.")
    income: list[AccountTotal]
    expenses: list[AccountTotal]
    income_total: dict[str, str]
    expense_total: dict[str, str]
    net: dict[str, str]
    savings_rate: str | None = Field(default=None, description="Net as a percent of income. Only given when everything is in one currency.")
    previous_start: dt.date | None = None
    previous_end: dt.date | None = None
    periods: list[PeriodTotal] = Field(default_factory=list, description="The same totals per week or month, when an interval is asked for.")
    interval: Literal["week", "month"] | None = None
