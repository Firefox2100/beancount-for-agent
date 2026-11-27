import datetime as dt
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from beancount_mcp.models.budgets import Budget, BudgetId
from beancount_mcp.models.goals import Goal, GoalId
from beancount_mcp.models.common import AccountName, Amount, FiniteDecimal, Text
from beancount_mcp.models.recurring import Recurring, RecurringId

KindName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
PoolName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
RecipeId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


class AccountProfile(BaseModel):
    description: Text | None = None
    recipes: list[RecipeId] | None = None
    statement_day: int | None = Field(default=None, ge=1, le=31)
    due_day: int | None = Field(default=None, ge=1, le=31)
    autopay_from: AccountName | None = None
    pool: PoolName | None = None
    unbilled_account: AccountName | None = None
    interest_account: AccountName | None = Field(
        default=None, description="Where interest is booked: income for savings, expense for loans."
    )
    cash_account: AccountName | None = Field(
        default=None, description="Settlement account of a brokerage account."
    )
    gains_account: AccountName | None = None
    interest_rate: FiniteDecimal | None = Field(default=None, description="Annual rate in percent. Informational.")
    maturity_date: dt.date | None = None


class Pool(BaseModel):
    limit: Amount


class Profile(BaseModel):
    accounts: dict[AccountName, AccountProfile] = Field(default_factory=dict)
    pools: dict[PoolName, Pool] = Field(default_factory=dict)
    recurring: dict[RecurringId, Recurring] = Field(default_factory=dict)
    budgets: dict[BudgetId, Budget] = Field(default_factory=dict)
    goals: dict[GoalId, Goal] = Field(default_factory=dict)


class ProfileView(BaseModel):
    profile: Profile
    version: str
    warnings: list[str] = Field(default_factory=list)


class RecipeInfo(BaseModel):
    id: str
    title: str
    description: str
    kinds: list[str]
    params_schema: dict


class KindInfo(BaseModel):
    name: str
    description: str
    recipes: list[str]
