import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import (
    AddDirective,
    AddTransaction,
    BalanceAssertion,
    Batch,
    Operation,
    Posting,
    TransactionInput,
)
from beancount_mcp.models.common import AccountName, Amount, Rate, Tag, Text
from beancount_mcp.recipes.base import Recipe, RecipeContext
from beancount_mcp.recipes.helpers import RATE_DESCRIPTION, DatedParams, Money, amount_of, exchange, negated
from beancount_mcp.recipes.registry import RecipeRegistry

KIND = "credit_card"
_negated = negated


def _unbilled_account(context: RecipeContext) -> str:
    return context.profile.unbilled_account or f"{context.account}:Unbilled"


class PurchaseParams(DatedParams):
    expense_account: AccountName
    amount: Money = Field(description="What was bought, in its own currency. A bare number means the card's only currency.")
    billed_amount: Money | None = Field(
        default=None,
        description="Set when the card converted the purchase into one of its own currencies at purchase time.",
    )
    payee: Text | None = None
    narration: Text = ""
    tags: list[Tag] = Field(default_factory=list)


def _purchase_charge(params: PurchaseParams, context: RecipeContext) -> tuple[Amount, str, dict[str, str]]:
    """The amount to charge, the liability account it goes to, and any metadata."""
    card_currencies = context.currencies(context.account)
    amount = amount_of(params.amount, card_currencies, "amount")
    meta: dict[str, str] = {}

    if params.billed_amount is not None:
        billed = amount_of(params.billed_amount, card_currencies, "billed_amount")
        if billed.currency not in card_currencies:
            raise RecipeError(f"the card is billed in {', '.join(card_currencies)}, not {billed.currency}")
        if billed.currency != amount.currency:
            meta["original-amount"] = f"{amount.number} {amount.currency}"
        return billed, context.account, meta
    if amount.currency in card_currencies:
        return amount, context.account, meta
    liability = _unbilled_account(context)
    context.require_open(liability)
    return amount, liability, meta


def compile_purchase(params: PurchaseParams, context: RecipeContext) -> Operation:
    context.require_open(params.expense_account)
    charge, liability, meta = _purchase_charge(params, context)

    return AddTransaction(
        transaction=TransactionInput(
            date=params.date,
            payee=params.payee,
            narration=params.narration,
            tags=params.tags,
            meta=meta,
            postings=[
                Posting(account=params.expense_account, units=charge),
                Posting(account=liability, units=_negated(charge)),
            ],
        )
    )


class RefundParams(PurchaseParams):
    expense_account: AccountName = Field(description="The expense the refund reverses.")


def compile_refund(params: RefundParams, context: RecipeContext) -> Operation:
    """A purchase with every sign reversed, billed in the same ways."""
    operation = compile_purchase(params, context)
    for posting in operation.transaction.postings:
        posting.units = _negated(posting.units)
    return operation


class Conversion(BaseModel):
    unbilled: Amount = Field(description="Amount waiting in the unbilled account, in its original currency.")
    billed: Money | None = Field(
        default=None, description="Amount the statement bills for it, in a currency of the card. Give this or `rate`."
    )
    rate: Rate | None = Field(default=None, description=RATE_DESCRIPTION)


class CloseStatementParams(DatedParams):
    conversions: list[Conversion] = Field(min_length=1)
    statement_balances: list[Money] = Field(
        default_factory=list,
        description="Optional total owed per currency after closing; checked with a balance assertion the next day.",
    )
    narration: Text = "Statement"


def compile_close_statement(params: CloseStatementParams, context: RecipeContext) -> Operation:
    card_currencies = context.currencies(context.account)
    unbilled_account = _unbilled_account(context)
    context.require_open(unbilled_account)
    owed = {currency: -number for currency, number in context.balance(unbilled_account).items()}

    postings: list[Posting] = []
    converting: dict[str, Decimal] = {}
    for conversion in params.conversions:
        unbilled = amount_of(conversion.unbilled, [], "unbilled")
        targets = [c for c in card_currencies if c != unbilled.currency]
        if conversion.billed is None and conversion.rate is None:
            raise RecipeError("give the billed amount or a rate")
        billed = exchange(unbilled, conversion.billed, conversion.rate, targets, "billed")
        if billed.currency not in card_currencies:
            raise RecipeError(f"the card is billed in {', '.join(card_currencies)}, not {billed.currency}")
        if unbilled.currency == billed.currency:
            raise RecipeError("unbilled and billed amounts must be in different currencies")
        conversion = Conversion(unbilled=unbilled, billed=billed)
        currency = unbilled.currency
        converting[currency] = converting.get(currency, Decimal(0)) + conversion.unbilled.number
        postings.append(
            Posting(
                account=unbilled_account,
                units=conversion.unbilled,
                price=Amount(
                    number=conversion.billed.number / conversion.unbilled.number,
                    currency=conversion.billed.currency,
                ),
            )
        )
        postings.append(Posting(account=context.account, units=_negated(conversion.billed)))

    for currency, amount in converting.items():
        if owed.get(currency, Decimal(0)) < amount:
            raise RecipeError(f"only {owed.get(currency, Decimal(0))} {currency} is unbilled, cannot convert {amount}")

    transaction = AddTransaction(
        transaction=TransactionInput(date=params.date, narration=params.narration, postings=postings)
    )
    if not params.statement_balances:
        return transaction
    day_after = params.date + dt.timedelta(days=1)
    assertions = [
        _balance_assertion(day_after, context.account, _negated(amount_of(balance, [], "statement_balances")))
        for balance in params.statement_balances
    ]
    return Batch(operations=[transaction, *assertions])


def _balance_assertion(date: dt.date, account: str, amount: Amount):
    return AddDirective(directive=BalanceAssertion(date=date, account=account, amount=amount))


class Payment(BaseModel):
    paid: Money = Field(description="Amount debited from the paying account.")
    cleared: Money | None = Field(
        default=None,
        description="Amount of the card bill it clears, in a currency of the card. Defaults to `paid` when that is a card currency.",
    )
    rate: Rate | None = Field(default=None, description=RATE_DESCRIPTION)


class PayCardParams(DatedParams):
    payments: list[Payment] = Field(min_length=1)
    from_account: AccountName | None = Field(
        default=None, description="Paying account. Defaults to the card's configured autopay account."
    )
    narration: Text = "Card payment"


def compile_pay_card(params: PayCardParams, context: RecipeContext) -> Operation:
    source = params.from_account or context.profile.autopay_from
    if source is None:
        raise RecipeError("no paying account given and the card has no autopay account configured")
    context.require_open(source)
    card_currencies = context.currencies(context.account)

    postings: list[Posting] = []
    for payment in params.payments:
        paid = amount_of(payment.paid, context.currencies(source), "paid")
        cleared = exchange(paid, payment.cleared, payment.rate, card_currencies, "cleared")
        if cleared.currency not in card_currencies:
            raise RecipeError(f"the card is billed in {', '.join(card_currencies)}, not {cleared.currency}")
        price = None if paid.currency == cleared.currency else Amount(
            number=paid.number / cleared.number, currency=paid.currency
        )
        postings.append(Posting(account=source, units=_negated(paid)))
        postings.append(Posting(account=context.account, units=cleared, price=price))

    return AddTransaction(
        transaction=TransactionInput(date=params.date, narration=params.narration, postings=postings)
    )


def register(registry: RecipeRegistry) -> None:
    kinds = frozenset({KIND})
    registry.describe_kind(
        KIND, "Credit card, possibly billed in several currencies, with an optional shared credit limit."
    )
    registry.register(Recipe(
        "refund", "Card refund", "Money returned to the card for an earlier purchase.",
        kinds, RefundParams, compile_refund,
    ))
    registry.register(Recipe(
        "purchase", "Card purchase",
        "Record a purchase on the card, billed in the purchase currency or converted at purchase time.",
        kinds, PurchaseParams, compile_purchase,
    ))
    registry.register(Recipe(
        "close_statement", "Close statement",
        "Convert unbilled foreign-currency purchases into the amounts the statement bills.",
        kinds, CloseStatementParams, compile_close_statement,
    ))
    registry.register(Recipe(
        "pay_card", "Pay card bill",
        "Pay the card bill from another account, in either or both currencies.",
        kinds, PayCardParams, compile_pay_card,
    ))
