import re
from enum import StrEnum

from pydantic import BaseModel, Field

from beancount_mcp.models.common import CurrencyCode, Text

LEDGER_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
LEDGER_ID_RE = re.compile(LEDGER_ID_PATTERN)


class Layout(StrEnum):
    SINGLE = "single"
    YEARLY = "yearly"
    MONTHLY = "monthly"


class LedgerError(BaseModel):
    message: str
    filename: str | None = None
    lineno: int | None = None


class LedgerInfo(BaseModel):
    id: str
    layout: Layout
    version: str


class LedgerStatus(LedgerInfo):
    errors: list[LedgerError]


class CreateLedgerRequest(BaseModel):
    id: str = Field(pattern=LEDGER_ID_PATTERN)
    title: Text | None = None
    operating_currencies: list[CurrencyCode] = Field(default_factory=list)
