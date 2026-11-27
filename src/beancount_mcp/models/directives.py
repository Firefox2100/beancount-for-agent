import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

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


class DocumentDirective(BaseModel):
    """A file linked to an account on a date, such as a receipt. The path is relative to the ledger folder."""

    kind: Literal["document"] = "document"
    date: dt.date
    account: AccountName
    path: Text

    @field_validator("path")
    @classmethod
    def _inside_documents(cls, value: str) -> str:
        parts = value.split("/")
        if parts[0] != "documents" or len(parts) < 2 or any(p in ("", ".", "..") for p in parts) or "\\" in value:
            raise ValueError("a document lives in the ledger's documents folder, for example documents/receipts/2026/lunch.jpg")
        return value


class EventDirective(BaseModel):
    kind: Literal["event"] = "event"
    date: dt.date
    type: Text
    description: Text


Directive = Annotated[
    BalanceAssertion | PadDirective | PriceDirective | CommodityDirective | NoteDirective | DocumentDirective | EventDirective,
    Field(discriminator="kind"),
]


class Record(BaseModel):
    id: str
    directive: Directive


class RecordPage(BaseModel):
    total: int
    items: list[Record]
