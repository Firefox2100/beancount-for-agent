import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from beancount_mcp.models.common import AccountName, Amount, CurrencyCode, FiniteDecimal, Text


class BalanceAssertion(BaseModel):
    kind: Literal["balance"] = "balance"
    date: dt.date
    account: AccountName
    amount: Amount
    tolerance: FiniteDecimal | None = None


class PadDirective(BaseModel):
    kind: Literal["pad"] = "pad"
    date: dt.date
    account: AccountName
    source_account: AccountName


class PriceDirective(BaseModel):
    kind: Literal["price"] = "price"
    date: dt.date
    currency: CurrencyCode
    amount: Amount


class CommodityDirective(BaseModel):
    kind: Literal["commodity"] = "commodity"
    date: dt.date
    currency: CurrencyCode


class NoteDirective(BaseModel):
    kind: Literal["note"] = "note"
    date: dt.date
    account: AccountName
    comment: Text


class EventDirective(BaseModel):
    kind: Literal["event"] = "event"
    date: dt.date
    type: Text
    description: Text


Directive = Annotated[
    BalanceAssertion | PadDirective | PriceDirective | CommodityDirective | NoteDirective | EventDirective,
    Field(discriminator="kind"),
]


class Record(BaseModel):
    id: str
    directive: Directive


class RecordPage(BaseModel):
    total: int
    items: list[Record]
