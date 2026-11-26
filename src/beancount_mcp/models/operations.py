import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from beancount_mcp.models.accounts import OpenAccountRequest
from beancount_mcp.models.common import AccountName, Amount
from beancount_mcp.models.details import AccountDetails, DetailName
from beancount_mcp.models.directives import Directive
from beancount_mcp.models.transactions import TransactionInput


class AddTransaction(BaseModel):
    kind: Literal["add_transaction"] = "add_transaction"
    transaction: TransactionInput


class UpdateTransaction(BaseModel):
    kind: Literal["update_transaction"] = "update_transaction"
    id: str
    transaction: TransactionInput


class DeleteTransaction(BaseModel):
    kind: Literal["delete_transaction"] = "delete_transaction"
    id: str


class OpenAccount(OpenAccountRequest):
    kind: Literal["open_account"] = "open_account"


class SetAccountDetails(BaseModel):
    kind: Literal["set_account_details"] = "set_account_details"
    account: AccountName
    set: AccountDetails = Field(default_factory=AccountDetails)
    clear: list[DetailName] = Field(default_factory=list)


class CloseAccount(BaseModel):
    kind: Literal["close_account"] = "close_account"
    account: AccountName
    date: dt.date


class AddDirective(BaseModel):
    kind: Literal["add_directive"] = "add_directive"
    directive: Directive


class UpdateDirective(BaseModel):
    kind: Literal["update_directive"] = "update_directive"
    id: str
    directive: Directive


class DeleteDirective(BaseModel):
    kind: Literal["delete_directive"] = "delete_directive"
    id: str


class Reconcile(BaseModel):
    """Assert an account's balance, optionally padding the difference from another account."""

    kind: Literal["reconcile"] = "reconcile"
    account: AccountName
    date: dt.date
    amount: Amount
    pad_account: AccountName | None = None


BatchMember = Annotated[
    AddTransaction | OpenAccount | CloseAccount | AddDirective | Reconcile,
    Field(discriminator="kind"),
]


class Batch(BaseModel):
    """Several additions applied as one atomic change."""

    kind: Literal["batch"] = "batch"
    operations: list[BatchMember] = Field(min_length=1)


Operation = Annotated[
    AddTransaction
    | UpdateTransaction
    | DeleteTransaction
    | OpenAccount
    | CloseAccount
    | SetAccountDetails
    | AddDirective
    | UpdateDirective
    | DeleteDirective
    | Reconcile
    | Batch,
    Field(discriminator="kind"),
]
