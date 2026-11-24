"""Recipes for borrowed money: mortgages, personal and student loans."""

from decimal import Decimal

from pydantic import Field

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AddTransaction, Operation, Posting, TransactionInput
from beancount_mcp.models.common import AccountName, Amount, Text
from beancount_mcp.recipes.base import Recipe, RecipeContext
from beancount_mcp.recipes.helpers import DatedParams, Money, Split, amount_of, exchange, two_legs
from beancount_mcp.recipes.registry import RecipeRegistry

KIND = "loan"


class DrawdownParams(DatedParams):
    to_account: AccountName = Field(description="Account that receives the money.")
    amount: Money
    received: Money | None = Field(default=None, description="What arrives, when it is another currency.")
    narration: Text = "Loan drawdown"


def compile_drawdown(params: DrawdownParams, context: RecipeContext) -> Operation:
    context.require_open(params.to_account)
    owed = amount_of(params.amount, context.currencies(context.account), "amount")
    received = exchange(owed, params.received, None, context.currencies(params.to_account), "received")
    return AddTransaction(
        transaction=TransactionInput(
            date=params.date,
            narration=params.narration,
            postings=two_legs(context.account, owed, params.to_account, received, base_sign=-1),
        )
    )


class RepayParams(DatedParams):
    from_account: AccountName
    principal: Money | None = Field(default=None, description="Part that reduces the loan. Give this or `payment`.")
    payment: Money | None = Field(
        default=None, description="Total paid, including interest and fees. Give this or `principal`."
    )
    interest: Money | None = None
    interest_account: AccountName | None = Field(
        default=None, description="Defaults to the loan's configured interest account."
    )
    fees: list[Split] = Field(default_factory=list)
    narration: Text = "Loan repayment"


def compile_repay(params: RepayParams, context: RecipeContext) -> Operation:
    context.require_open(params.from_account)
    if params.principal is None and params.payment is None:
        raise RecipeError("give the principal or the total payment")
    currencies = context.currencies(context.account)
    anchor = amount_of(params.principal if params.principal is not None else params.payment, currencies, "amount")
    currency = anchor.currency

    interest = Decimal(0)
    if params.interest is not None:
        interest = amount_of(params.interest, [currency], "interest").number
    fees = []
    for split in params.fees:
        context.require_open(split.account)
        fees.append((split.account, amount_of(split.amount, [currency], "fee")))
    extra = interest + sum((amount.number for _, amount in fees), Decimal(0))

    if params.principal is not None:
        principal = anchor.number
        payment = principal + extra
        if params.payment is not None and amount_of(params.payment, [currency], "payment").number != payment:
            raise RecipeError(f"principal {principal} plus interest and fees {extra} is {payment}, not the payment given")
    else:
        payment = anchor.number
        principal = payment - extra
    if principal <= 0:
        raise RecipeError("interest and fees leave nothing to reduce the loan")

    postings = [
        Posting(account=params.from_account, units=Amount(number=-payment, currency=currency)),
        Posting(account=context.account, units=Amount(number=principal, currency=currency)),
    ]
    if interest:
        account = params.interest_account or context.profile.interest_account
        if account is None:
            raise RecipeError("no interest account given and the loan has none configured")
        context.require_open(account)
        postings.append(Posting(account=account, units=Amount(number=interest, currency=currency)))
    postings += [Posting(account=name, units=amount) for name, amount in fees]
    return AddTransaction(transaction=TransactionInput(date=params.date, narration=params.narration, postings=postings))


def register(registry: RecipeRegistry) -> None:
    kinds = frozenset({KIND})
    registry.describe_kind("loan", "Money owed in instalments: mortgage, personal or student loan.")
    registry.register(Recipe(
        "drawdown", "Draw down loan", "Receive loan money into another account.", kinds, DrawdownParams, compile_drawdown
    ))
    registry.register(Recipe(
        "repay", "Repay loan",
        "Make a repayment, split into principal, interest and fees. Give the principal or the total.",
        kinds, RepayParams, compile_repay,
    ))
