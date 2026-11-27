import datetime as dt

from pydantic import BaseModel, Field

from beancount_mcp.models.common import Amount


class OpenItem(BaseModel):
    link: str
    account: str
    opened: dt.date
    payee: str | None = None
    narration: str = ""
    balances: dict[str, str] = Field(description="What is still open, per currency. Positive on a receivable, negative on a payable.")
    transactions: int


class OpenItems(BaseModel):
    account: str
    items: list[OpenItem]
    unlinked: dict[str, str] = Field(
        description="Net of postings that carry no link, such as a payment that was not matched to an item."
    )
    balance: dict[str, str]


class DueItem(BaseModel):
    account: str
    description: str | None = None
    owed: dict[str, str] = Field(description="Amount owed per currency, billed or not.")
    unbilled: dict[str, str] = Field(default_factory=dict)
    next_statement: dt.date | None = None
    due_date: dt.date | None = None
    days_until_due: int | None = None
    autopay_from: str | None = None


class PoolMember(BaseModel):
    account: str
    owed: dict[str, str]


class PoolStatus(BaseModel):
    name: str
    limit: Amount
    used: str
    available: str
    members: list[PoolMember]
    unconverted: dict[str, str] = Field(
        default_factory=dict,
        description="Owed amounts in currencies with no price to the limit currency. They are not counted in `used`.",
    )


class ReferenceRateStatus(BaseModel):
    provider: str = "frankfurter"
    enabled: bool
    base_currency: str | None = None
    observed_on: dt.date | None = None
    fetched_at: dt.datetime | None = None
    state: str = Field(description="disabled, empty, fresh, stale, refreshing, or unavailable")
    covered_currencies: list[str] = Field(default_factory=list)
    missing_currencies: list[str] = Field(default_factory=list)
    message: str | None = None


class ReferenceValue(BaseModel):
    number: str
    currency: str
    approximate: bool = True


class PositionTotal(BaseModel):
    original: dict[str, str] = Field(default_factory=dict)
    reference_value: ReferenceValue | None = None


class PositionPoint(BaseModel):
    date: dt.date
    assets: PositionTotal
    liabilities: PositionTotal
    net: PositionTotal
    valuation: ReferenceRateStatus


class AllocationItem(BaseModel):
    account: str
    original: dict[str, str]
    reference_value: ReferenceValue | None = None
    share: str | None = None


class FinancialPosition(BaseModel):
    ledger: str
    ledger_version: str
    interval: str
    base_currency: str
    points: list[PositionPoint]
    allocation: list[AllocationItem]
    valuation: ReferenceRateStatus
