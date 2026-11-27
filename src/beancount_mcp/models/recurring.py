"""Things that happen on a schedule: rent, a subscription, a salary. The service never posts them by itself."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from beancount_mcp.models.common import AccountName, Amount, Text

RecurringId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Every = Literal["week", "month", "year"]


class Recurring(BaseModel):
    """A schedule and what happens on it. Money moves from `from_account` to `to_account`, as in a transfer.

    Rent is Assets:Bank to Expenses:Rent. A salary is Income:Salary to Assets:Bank.
    """

    title: Text
    from_account: AccountName
    to_account: AccountName
    amount: Amount = Field(description="What each occurrence is. For a bill that varies, an estimate.")
    every: Every = "month"
    interval: int = Field(default=1, ge=1, le=52, description="Every this many weeks, months or years.")
    start: dt.date = Field(description="The first due date. It also fixes the day of the month, clamped in short months.")
    end: dt.date | None = Field(default=None, description="No occurrence after this date.")
    payee: Text | None = None
    narration: Text | None = None
    variable: bool = Field(default=False, description="The amount changes each time (a utility bill): it is not used to recognise a payment.")

    @model_validator(mode="after")
    def _distinct(self):
        if self.from_account == self.to_account:
            raise ValueError("from_account and to_account must differ")
        return self


class Occurrence(BaseModel):
    date: dt.date
    status: Literal["overdue", "due", "upcoming"] = Field(description="Overdue: before today and not recorded. Due: today.")


class RecurringStatus(BaseModel):
    id: str
    title: str
    schedule: str
    from_account: str
    to_account: str
    amount: Amount
    variable: bool
    payee: str | None = None
    narration: str | None = None
    next_due: dt.date | None = None
    last_paid: dt.date | None = Field(default=None, description="The latest recorded payment.")
    occurrences: list[Occurrence] = Field(description="Not yet recorded: overdue ones, then those coming up in the window.")


class RecurringSuggestion(BaseModel):
    """A pattern found in the history that no recurring item covers yet."""

    id: str
    recurring: Recurring
    seen: int = Field(description="How many times in a row it was seen at this spacing.")
    last_seen: dt.date
