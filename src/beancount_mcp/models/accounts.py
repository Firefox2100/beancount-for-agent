import datetime as dt
from typing import Annotated

from pydantic import BaseModel, Field

from beancount_mcp.models.common import AccountName, Amount, CurrencyCode
from beancount_mcp.models.details import AccountDetails
from beancount_mcp.models.profile import KindName

BookingMethod = Annotated[str, Field(pattern=r"^(STRICT|STRICT_WITH_SIZE|NONE|AVERAGE|FIFO|LIFO|HIFO)$")]


class AccountInfo(BaseModel):
    name: str
    open_date: dt.date
    close_date: dt.date | None = None
    currencies: list[str] = Field(default_factory=list)
    booking: str | None = None
    type: str | None = None
    description: str | None = None
    recipes: list[str] = Field(default_factory=list)
    details: dict[str, str] = Field(default_factory=dict, description="Bank details, keyed by field name. Sensitive ones are masked for agents.")


class OpenAccountRequest(BaseModel):
    account: AccountName
    date: dt.date
    currencies: list[CurrencyCode] = Field(default_factory=list)
    booking: BookingMethod | None = None
    type: KindName | None = None
    details: AccountDetails | None = None


class CloseAccountRequest(BaseModel):
    date: dt.date


class AccountBalance(BaseModel):
    account: str
    balances: dict[str, str]


class ReconcileRequest(BaseModel):
    date: dt.date
    amount: Amount
    pad_account: AccountName | None = None
