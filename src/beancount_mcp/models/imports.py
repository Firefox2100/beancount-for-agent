"""Bank statements as the service holds them: one canonical shape, whatever file format they arrived in."""

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field

from beancount_mcp.models.common import CurrencyCode, FiniteDecimal


class StatementLine(BaseModel):
    number: int = Field(default=0, description="Position in the statement, from 1. Proposals refer to lines by it.")
    date: dt.date
    amount: FiniteDecimal = Field(description="From the account holder's side: money in is positive, money out is negative.")
    description: str = ""
    payee: str | None = None
    reference: str | None = Field(default=None, description="The bank's own id for the transaction, when the file has one.")


class Statement(BaseModel):
    """What an importer returns. Importers only read: they never see the ledger."""

    format: str = Field(description="Id of the importer that read it.")
    account_id: str | None = Field(default=None, description="The account as the file names it (IBAN, account number).")
    currency: CurrencyCode
    opening_balance: FiniteDecimal | None = None
    closing_balance: FiniteDecimal | None = None
    start: dt.date | None = None
    end: dt.date | None = None
    lines: list[StatementLine]


class LineStatus(StrEnum):
    NEW = "new"
    IMPORTED = "imported"
    POSSIBLE_DUPLICATE = "possible_duplicate"


class StatementImport(BaseModel):
    """A statement a person uploaded for one account, waiting to be turned into a proposal."""

    id: str
    filename: str
    account: str
    created_at: dt.datetime
    statement: Statement
    warnings: list[str] = Field(default_factory=list)
    change_ids: list[str] = Field(default_factory=list, description="Proposals made from this statement.")


class ReviewedLine(StatementLine):
    status: LineStatus
    matches: str | None = Field(default=None, description="The ledger transaction it was matched with, when it was.")


class ImportSummary(BaseModel):
    id: str
    filename: str
    account: str
    format: str
    currency: str
    start: dt.date | None = None
    end: dt.date | None = None
    lines: int
    new: int
    warnings: list[str] = Field(default_factory=list)
    change_ids: list[str] = Field(default_factory=list)


class ImportReview(ImportSummary):
    """A statement with each line checked against what the ledger already holds."""

    opening_balance: FiniteDecimal | None = None
    closing_balance: FiniteDecimal | None = None
    items: list[ReviewedLine]
    omitted: int = Field(default=0, description="Lines left out of `items` by the limit.")


class FormatInfo(BaseModel):
    id: str
    title: str
