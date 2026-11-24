"""Recipes for items that stay open until a later transaction settles them.

Reimbursement claims, loans to people, invoices and bills to pay all work the
same way. One transaction opens the item on a receivable or payable account and
a later one settles it. Both carry the same Beancount link, so matching shows up
in any other Beancount tool.
"""

from decimal import Decimal

from pydantic import Field

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AddTransaction, Operation, Posting, TransactionInput
from beancount_mcp.models.common import AccountName, Amount, Tag, Text
from beancount_mcp.recipes.base import Recipe, RecipeContext
from beancount_mcp.recipes.helpers import DatedParams, Money, amount_of, auto_link
from beancount_mcp.recipes.registry import RecipeRegistry

LINK_DESCRIPTION = "Link that ties the opening and the settling transactions together. Generated when omitted."


class OpenParams(DatedParams):
    counter_account: AccountName
    amount: Money
    payee: Text | None = Field(default=None, description="Who owes or is owed.")
    narration: Text = ""
    link: Tag | None = Field(default=None, description=LINK_DESCRIPTION)
    tags: list[Tag] = Field(default_factory=list)


def _open_item(params: OpenParams, context: RecipeContext, prefix: str, sign: int) -> Operation:
    """`sign` is +1 when the item is an asset (money owed to us) and -1 when it is a liability."""
    context.require_open(params.counter_account)
    amount = amount_of(params.amount, context.currencies(context.account), "amount")
    link = params.link or auto_link(prefix, context.account, params.counter_account, params.date, amount.number, params.payee)
    postings = [
        Posting(account=context.account, units=Amount(number=sign * amount.number, currency=amount.currency)),
        Posting(account=params.counter_account, units=Amount(number=-sign * amount.number, currency=amount.currency)),
    ]
    return AddTransaction(
        transaction=TransactionInput(
            date=params.date, payee=params.payee, narration=params.narration, tags=params.tags, links=[link], postings=postings
        )
    )


class SettleParams(DatedParams):
    counter_account: AccountName = Field(description="Account the money moves to or from.")
    amount: Money | None = Field(default=None, description="Defaults to everything currently open on the account.")
    adjustment: Money | None = Field(
        default=None, description="Part forgiven or discounted instead of paid. It is booked to `adjustment_account`."
    )
    adjustment_account: AccountName | None = None
    payee: Text | None = None
    narration: Text = ""
    link: Tag | None = Field(default=None, description="The link of the item being settled.")
    tags: list[Tag] = Field(default_factory=list)


def _settle(params: SettleParams, context: RecipeContext, sign: int, default_narration: str) -> Operation:
    """`sign` is +1 for a receivable (settling reduces the asset) and -1 for a payable."""
    context.require_open(params.counter_account)
    currencies = context.currencies(context.account)
    if params.amount is None:
        open_amounts = {c: n for c, n in context.balance(context.account).items() if sign * n > 0}
        if len(open_amounts) != 1:
            raise RecipeError("give the amount: the account does not hold exactly one open currency")
        (currency, number), = open_amounts.items()
        paid = Amount(number=abs(number), currency=currency)
        if params.adjustment is not None:
            paid = Amount(number=paid.number - amount_of(params.adjustment, [currency], "adjustment").number, currency=currency)
            if paid.number <= 0:
                raise RecipeError("the adjustment leaves nothing to settle")
    else:
        paid = amount_of(params.amount, currencies, "amount")

    adjustment = None
    if params.adjustment is not None:
        if params.adjustment_account is None:
            raise RecipeError("adjustment_account is required with an adjustment")
        context.require_open(params.adjustment_account)
        adjustment = amount_of(params.adjustment, [paid.currency], "adjustment")
        if adjustment.currency != paid.currency:
            raise RecipeError("the adjustment must be in the same currency as the payment")

    cleared = paid.number + (adjustment.number if adjustment else Decimal(0))
    currency = paid.currency
    postings = [
        Posting(account=params.counter_account, units=Amount(number=sign * paid.number, currency=currency)),
        Posting(account=context.account, units=Amount(number=-sign * cleared, currency=currency)),
    ]
    if adjustment:
        postings.append(
            Posting(account=params.adjustment_account, units=Amount(number=sign * adjustment.number, currency=currency))
        )
    return AddTransaction(
        transaction=TransactionInput(
            date=params.date,
            payee=params.payee,
            narration=params.narration or default_narration,
            tags=params.tags,
            links=[params.link] if params.link else [],
            postings=postings,
        )
    )


def register(registry: RecipeRegistry) -> None:
    receivable = frozenset({"receivable"})
    payable = frozenset({"payable"})
    registry.describe_kind(
        "receivable", "Money owed to you: a reimbursement claim, a loan to a person or an unpaid invoice."
    )
    registry.describe_kind("payable", "Money you owe on a bill or to a supplier, not yet paid.")

    class Lend(OpenParams):
        counter_account: AccountName = Field(description="Where the money came from, or the expense being claimed back.")

    class Invoice(OpenParams):
        counter_account: AccountName = Field(description="The income account the invoice earns.")

    class Bill(OpenParams):
        counter_account: AccountName = Field(description="The expense account the bill belongs to.")

    registry.register(Recipe(
        "lend", "Lend or claim",
        "Money you paid that someone owes you back, such as a loan or an expense to be reimbursed.",
        receivable, Lend, lambda p, c: _open_item(p, c, "claim", +1),
    ))
    registry.register(Recipe(
        "invoice", "Invoice", "Record an invoice you issued, earning income that is not yet paid.",
        receivable, Invoice, lambda p, c: _open_item(p, c, "invoice", +1),
    ))
    registry.register(Recipe(
        "collect", "Collect payment",
        "Money received against an open item. Leave the amount out to settle everything open.",
        receivable, SettleParams, lambda p, c: _settle(p, c, +1, "Payment received"),
    ))
    registry.register(Recipe(
        "receive_bill", "Record a bill", "A bill you owe and have not paid yet.",
        payable, Bill, lambda p, c: _open_item(p, c, "bill", -1),
    ))
    registry.register(Recipe(
        "pay_bill", "Pay a bill", "Pay an open bill. Leave the amount out to pay everything open.",
        payable, SettleParams, lambda p, c: _settle(p, c, -1, "Bill payment"),
    ))
