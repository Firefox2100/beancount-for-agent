"""Spending limits on expense groups. A budget is a limit and a period; the service works out how it is going."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from beancount_mcp.models.common import AccountName, Amount, Text
from beancount_mcp.models.conversion import Converted

BudgetId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Period = Literal["week", "month", "year"]
State = Literal["ok", "ahead", "over"]


class Budget(BaseModel):
    """A limit on what is spent under one expense account, such as Expenses:Food, per period."""

    account: AccountName = Field(description="An expense account or group. Everything under it counts.")
    amount: Amount = Field(description="The limit for one period.")
    every: Period = "month"
    start_day: int = Field(default=1, ge=1, le=28, description="Months only: the day a month starts on, for a pay cycle.")
    title: Text | None = None

    @field_validator("account")
    @classmethod
    def _expenses_only(cls, value: str) -> str:
        if value.split(":")[0] != "Expenses":
            raise ValueError("a budget limits spending, so the account must be under Expenses")
        return value


class PeriodSpent(BaseModel):
    start: dt.date
    end: dt.date
    spent: str
    over: bool


class BudgetStatus(BaseModel):
    id: str
    title: str
    account: str
    limit: Amount
    every: Period
    start: dt.date = Field(description="Where the current period started.")
    end: dt.date
    spent: str = Field(description="In the limit's currency, this period so far, including other currencies converted at today's rate.")
    approximate: bool = Field(default=False, description="True when `spent` includes converted amounts.")
    converted: list[Converted] = Field(default_factory=list)
    remaining: str = Field(description="Negative once over.")
    used_percent: str
    state: State = Field(description="over: past the limit. ahead: spending faster than the period is passing. ok: otherwise.")
    days_left: int
    projected: str = Field(description="Where the period ends at the current pace.")
    daily_allowance: str | None = Field(default=None, description="What can still be spent per remaining day, when there is anything left.")
    other_currencies: dict[str, str] = Field(default_factory=dict, description="Spending under the account in currencies with no rate available, not counted above.")
    history: list[PeriodSpent] = Field(default_factory=list, description="The periods before this one, latest first.")


class BudgetSuggestion(BaseModel):
    """A budget the history suggests: the average of recent whole months, rounded up."""

    id: str
    budget: Budget
    average: str
    months: int
