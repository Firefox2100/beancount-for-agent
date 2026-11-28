import datetime as dt
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

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


class AttachReceipt(BaseModel):
    """Link a stored receipt to a transaction: a `document` entry on its account and a `document` note on the transaction."""

    kind: Literal["attach_receipt"] = "attach_receipt"
    id: str = Field(description="The transaction.")
    path: str = Field(description="The receipt, relative to the ledger folder.")


OptionName = Literal["title", "operating_currency", "render_commas", "booking_method"]
BOOKING_METHODS = ("STRICT", "STRICT_WITH_SIZE", "NONE", "AVERAGE", "FIFO", "LIFO", "HIFO")


class SetOption(BaseModel):
    """Set or remove one of the ledger's options, the few that are safe to change here.

    `operating_currency` may appear several times: setting adds a currency and `remove` takes one away. The others
    have one value, which setting replaces and `remove` clears.
    """

    kind: Literal["set_option"] = "set_option"
    name: OptionName
    value: str = Field(min_length=1, max_length=200, pattern=r'^[^"\\\x00-\x1f]+$')
    remove: bool = False

    @model_validator(mode="after")
    def _valid_value(self):
        if self.name == "operating_currency" and not re.fullmatch(r"[A-Z][A-Z0-9'._-]{0,22}[A-Z0-9]?", self.value):
            raise ValueError("an operating currency is a currency code such as GBP")
        if self.name == "render_commas" and self.value not in ("TRUE", "FALSE"):
            raise ValueError("render_commas is TRUE or FALSE")
        if self.name == "booking_method" and self.value not in BOOKING_METHODS:
            raise ValueError(f"booking_method is one of {', '.join(BOOKING_METHODS)}")
        return self


ProfileItemKind = Literal["recipe", "recurring", "budget", "goal"]


class SetProfileItem(BaseModel):
    """Add, replace or (with no value) remove one item of the ledger's profile: a recipe, recurring item, budget or goal.

    It changes how the service treats the ledger, not the ledger's entries, so it is never applied without a person
    approving it, even when agent changes are otherwise applied at once.
    """

    kind: Literal["set_profile_item"] = "set_profile_item"
    item: ProfileItemKind
    id: str = Field(min_length=1, max_length=64)
    value: dict[str, Any] | None = Field(default=None, description="The item as `get_setup` describes it. Leave out to remove it.")


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
    | AttachReceipt
    | SetOption
    | SetProfileItem
    | Batch,
    Field(discriminator="kind"),
]
