"""Savings goals: a target amount held in some accounts, optionally by a date."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from beancount_mcp.models.common import AccountName, Amount, Text
from beancount_mcp.models.conversion import Converted

GoalId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]


class Goal(BaseModel):
    """Something to save up for. Progress is what the named accounts hold, so there is nothing to record by hand."""

    title: Text
    accounts: list[AccountName] = Field(min_length=1, description="Asset accounts or groups whose balances count towards it.")
    target: Amount
    by: dt.date | None = Field(default=None, description="When it should be reached.")
    monthly: Amount | None = Field(default=None, description="What is planned to be put aside each month. Only used to say when the target is reached.")

    @field_validator("accounts")
    @classmethod
    def _assets_only(cls, value: list[str]) -> list[str]:
        if any(name.split(":")[0] != "Assets" for name in value):
            raise ValueError("a goal counts what is saved, so its accounts must be under Assets")
        return value


class GoalStatus(BaseModel):
    id: str
    title: str
    accounts: list[str]
    target: Amount
    saved: str = Field(description="What the accounts hold, in the target's currency, other currencies converted at today's rate.")
    approximate: bool = False
    converted: list[Converted] = Field(default_factory=list)
    other_currencies: dict[str, str] = Field(default_factory=dict, description="Held in currencies with no rate available, not counted.")
    remaining: str = Field(description="Zero once reached.")
    percent: str
    reached: bool
    by: dt.date | None = None
    months_left: int | None = Field(default=None, description="Whole months until `by`. Zero when it is this month or past.")
    needed_monthly: str | None = Field(default=None, description="What has to be put aside each month to arrive on time.")
    planned_monthly: Amount | None = None
    projected: dt.date | None = Field(default=None, description="When the target is reached at the planned monthly amount.")
    state: Literal["reached", "on_track", "behind", "open"] = Field(
        description="reached; on_track: the plan arrives on time; behind: it does not, or there is no plan and time is short; open: no deadline."
    )
