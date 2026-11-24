"""Recipes for accounts that hold money: checking, savings, cash and wallets."""

from decimal import Decimal

from pydantic import BaseModel, Field

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AddTransaction, Operation, Posting, TransactionInput
from beancount_mcp.models.common import AccountName, Amount, FiniteDecimal, Tag, Text
from beancount_mcp.recipes.base import Recipe, RecipeContext
from beancount_mcp.recipes.helpers import (
    RATE_DESCRIPTION,
    DatedParams,
    Money,
    Split,
    amount_of,
    exchange,
    negated,
    two_legs,
)
from beancount_mcp.recipes.registry import RecipeRegistry

KINDS = ("checking", "savings", "cash", "ewallet")


class SpendParams(DatedParams):
    expense_account: AccountName
    amount: Money = Field(description="What was bought, in its own currency.")
    charged: Money | None = Field(
        default=None, description="What the account was debited, when that is another currency than `amount`."
    )
    rate: FiniteDecimal | None = Field(default=None, description=RATE_DESCRIPTION)
    payee: Text | None = None
    narration: Text = ""
    tags: list[Tag] = Field(default_factory=list)


def compile_spend(params: SpendParams, context: RecipeContext) -> Operation:
    context.require_open(params.expense_account)
    currencies = context.currencies(context.account)
    spent = amount_of(params.amount, currencies, "amount")
    charged = exchange(spent, params.charged, params.rate, currencies, "charged")
    return AddTransaction(
        transaction=TransactionInput(
            date=params.date,
            payee=params.payee,
            narration=params.narration,
            tags=params.tags,
            postings=two_legs(params.expense_account, spent, context.account, charged, base_sign=1),
        )
    )


class ReceiveParams(DatedParams):
    from_account: AccountName = Field(description="Where the money came from: income, another asset, a liability.")
    amount: Money = Field(description="What arrived in this account.")
    sent: Money | None = Field(
        default=None, description="What left the source, when that is another currency than `amount`."
    )
    rate: FiniteDecimal | None = Field(default=None, description=RATE_DESCRIPTION)
    payee: Text | None = None
    narration: Text = ""
    tags: list[Tag] = Field(default_factory=list)


def compile_receive(params: ReceiveParams, context: RecipeContext) -> Operation:
    context.require_open(params.from_account)
    received = amount_of(params.amount, context.currencies(context.account), "amount")
    sent = exchange(received, params.sent, params.rate, context.currencies(params.from_account), "sent")
    return AddTransaction(
        transaction=TransactionInput(
            date=params.date,
            payee=params.payee,
            narration=params.narration,
            tags=params.tags,
            postings=two_legs(context.account, received, params.from_account, sent, base_sign=1),
        )
    )


class TransferParams(DatedParams):
    to_account: AccountName
    amount: Money = Field(description="What leaves this account.")
    received: Money | None = Field(
        default=None, description="What arrives, when the other account holds another currency."
    )
    rate: FiniteDecimal | None = Field(default=None, description=RATE_DESCRIPTION)
    narration: Text = "Transfer"
    tags: list[Tag] = Field(default_factory=list)


def compile_transfer(params: TransferParams, context: RecipeContext) -> Operation:
    if params.to_account == context.account:
        raise RecipeError("cannot transfer to the same account")
    context.require_open(params.to_account)
    paid = amount_of(params.amount, context.currencies(context.account), "amount")
    received = exchange(paid, params.received, params.rate, context.currencies(params.to_account), "received")
    return AddTransaction(
        transaction=TransactionInput(
            date=params.date,
            narration=params.narration,
            tags=params.tags,
            postings=two_legs(context.account, paid, params.to_account, received, base_sign=-1),
        )
    )


class InterestParams(DatedParams):
    amount: Money = Field(description="Interest paid into the account, after any tax.")
    income_account: AccountName | None = Field(
        default=None, description="Defaults to the account's configured interest account."
    )
    tax_withheld: Money | None = None
    tax_account: AccountName | None = Field(default=None, description="Required when tax is withheld.")
    narration: Text = "Interest"


def compile_interest(params: InterestParams, context: RecipeContext) -> Operation:
    income = params.income_account or context.profile.interest_account
    if income is None:
        raise RecipeError("no income account given and the account has no interest account configured")
    context.require_open(income)
    currencies = context.currencies(context.account)
    net = amount_of(params.amount, currencies, "amount")
    postings = [Posting(account=context.account, units=net)]
    gross = net.number
    if params.tax_withheld is not None:
        if params.tax_account is None:
            raise RecipeError("tax_account is required when tax is withheld")
        context.require_open(params.tax_account)
        tax = amount_of(params.tax_withheld, [net.currency], "tax_withheld")
        if tax.currency != net.currency:
            raise RecipeError("tax_withheld must be in the same currency as the interest")
        postings.append(Posting(account=params.tax_account, units=tax))
        gross += tax.number
    postings.append(Posting(account=income, units=Amount(number=-gross, currency=net.currency)))
    return AddTransaction(
        transaction=TransactionInput(date=params.date, narration=params.narration, postings=postings)
    )


class SalaryParams(DatedParams):
    income_account: AccountName
    gross: Money | None = Field(default=None, description="Pay before deductions. Give this or `net`.")
    net: Money | None = Field(default=None, description="What was deposited. Give this or `gross`.")
    deductions: list[Split] = Field(
        default_factory=list, description="Tax, pension, insurance and so on, each to its own account."
    )
    payee: Text | None = None
    narration: Text = "Salary"
    tags: list[Tag] = Field(default_factory=list)


def compile_salary(params: SalaryParams, context: RecipeContext) -> Operation:
    context.require_open(params.income_account)
    if params.gross is None and params.net is None:
        raise RecipeError("give the gross or the net pay")
    given = params.gross if params.gross is not None else params.net
    currency_hint = context.currencies(context.account)
    anchor = amount_of(given, currency_hint, "gross" if params.gross is not None else "net")
    deductions = []
    for split in params.deductions:
        context.require_open(split.account)
        deductions.append((split.account, amount_of(split.amount, [anchor.currency], "deduction")))
    if any(amount.currency != anchor.currency for _, amount in deductions):
        raise RecipeError("deductions must be in the same currency as the pay")
    total = sum((amount.number for _, amount in deductions), Decimal(0))

    if params.gross is not None:
        gross = anchor.number
        net = gross - total
        if params.net is not None and amount_of(params.net, [anchor.currency], "net").number != net:
            raise RecipeError(f"gross {gross} less deductions {total} is {net}, not the net pay given")
    else:
        net = anchor.number
        gross = net + total
    if net <= 0:
        raise RecipeError("deductions leave nothing to deposit")

    currency = anchor.currency
    postings = [Posting(account=context.account, units=Amount(number=net, currency=currency))]
    postings += [Posting(account=name, units=amount) for name, amount in deductions]
    postings.append(Posting(account=params.income_account, units=Amount(number=-gross, currency=currency)))
    return AddTransaction(
        transaction=TransactionInput(
            date=params.date, payee=params.payee, narration=params.narration, tags=params.tags, postings=postings
        )
    )


def register(registry: RecipeRegistry) -> None:
    kinds = frozenset(KINDS)
    registry.describe_kind("checking", "Current or debit account that holds money and pays for things.")
    registry.describe_kind("savings", "Savings or fixed-rate deposit. Interest is booked as income.")
    registry.describe_kind("cash", "Physical cash.")
    registry.describe_kind("ewallet", "A prepaid balance or payment app wallet.")
    for recipe in (
        Recipe("spend", "Spend", "Pay for something from this account, also in another currency.",
               kinds, SpendParams, compile_spend),
        Recipe("receive", "Receive money", "Money arriving from income, another account or a person.",
               kinds, ReceiveParams, compile_receive),
        Recipe("transfer", "Transfer", "Move money to another account, converting currency if needed.",
               kinds, TransferParams, compile_transfer),
        Recipe("interest", "Interest", "Interest paid into the account, optionally with tax withheld.",
               kinds, InterestParams, compile_interest),
        Recipe("salary", "Salary", "Pay received with deductions. Give the gross or the net amount.",
               kinds, SalaryParams, compile_salary),
    ):
        registry.register(recipe)
