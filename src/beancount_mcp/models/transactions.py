import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from beancount_mcp.models.common import (
    AccountName,
    Amount,
    CurrencyCode,
    FiniteDecimal,
    MetaKey,
    Tag,
    Text,
)

RESERVED_META_KEYS = {"id", "filename", "lineno"}


class Cost(BaseModel):
    number: FiniteDecimal | None = None
    currency: CurrencyCode | None = None
    date: dt.date | None = None
    label: Text | None = None


class Posting(BaseModel):
    account: AccountName
    units: Amount | None = None
    cost: Cost | None = None
    price: Amount | None = None


class TransactionInput(BaseModel):
    date: dt.date
    flag: Literal["*", "!"] = "*"
    payee: Text | None = None
    narration: Text = ""
    tags: list[Tag] = Field(default_factory=list)
    links: list[Tag] = Field(default_factory=list)
    postings: list[Posting] = Field(min_length=2)
    meta: dict[MetaKey, Text] = Field(default_factory=dict)

    def model_post_init(self, __context) -> None:
        reserved = RESERVED_META_KEYS & self.meta.keys()
        if reserved:
            raise ValueError(f"reserved metadata keys: {sorted(reserved)}")


class Transaction(TransactionInput):
    id: str


class TransactionPage(BaseModel):
    total: int
    items: list[Transaction]
