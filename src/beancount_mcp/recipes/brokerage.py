"""Recipes for investment accounts that hold commodities."""

import datetime as dt
from decimal import Decimal

from pydantic import Field

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AddTransaction, Operation, Posting, TransactionInput
from beancount_mcp.models.common import AccountName, Amount, CurrencyCode, FiniteDecimal, Text
from beancount_mcp.models.transactions import Cost
from beancount_mcp.recipes.base import Recipe, RecipeContext
from beancount_mcp.recipes.helpers import DatedParams, Money, amount_of
from beancount_mcp.recipes.registry import RecipeRegistry

KIND = "brokerage"


def _cash_account(given: str | None, context: RecipeContext) -> str:
    account = given or context.profile.cash_account
    if account is None:
        raise RecipeError("no cash account given and the account has none configured")
    context.require_open(account)
    return account


class TradeParams(DatedParams):
    commodity: CurrencyCode = Field(description="What is traded, for example a ticker.")
    units: FiniteDecimal
    price: Money | None = Field(default=None, description="Per unit. Give this or `total`.")
    total: Money | None = Field(default=None, description="Whole amount of the trade, before fees. Give this or `price`.")
    cash_account: AccountName | None = Field(
        default=None, description="Where the money moves. Defaults to the account's configured cash account."
    )
    fee: Money | None = None
    fee_account: AccountName | None = Field(default=None, description="Required with a fee.")
    narration: Text = ""


def _trade_amounts(params: TradeParams, cash: str, context: RecipeContext) -> tuple[Decimal, Amount, Amount]:
    if params.units <= 0:
        raise RecipeError("units must be positive")
    units = params.units
    currencies = context.currencies(cash)
    if params.total is not None:
        total = amount_of(params.total, currencies, "total")
        return units, Amount(number=total.number / units, currency=total.currency), total
    if params.price is None:
        raise RecipeError("give the price per unit or the total")
    price = amount_of(params.price, currencies, "price")
    return units, price, Amount(number=price.number * units, currency=price.currency)


def _fee(params: TradeParams, currency: str, context: RecipeContext) -> Amount | None:
    if params.fee is None:
        return None
    if params.fee_account is None:
        raise RecipeError("fee_account is required with a fee")
    context.require_open(params.fee_account)
    fee = amount_of(params.fee, [currency], "fee")
    if fee.currency != currency:
        raise RecipeError("the fee must be in the trade currency")
    return fee


def compile_buy(params: TradeParams, context: RecipeContext) -> Operation:
    cash = _cash_account(params.cash_account, context)
    units, price, total = _trade_amounts(params, cash, context)
    fee = _fee(params, total.currency, context)
    paid = total.number + (fee.number if fee else Decimal(0))
    postings = [
        Posting(
            account=context.account,
            units=Amount(number=units, currency=params.commodity),
            cost=Cost(number=price.number, currency=price.currency),
        ),
        Posting(account=cash, units=Amount(number=-paid, currency=total.currency)),
    ]
    if fee:
        postings.append(Posting(account=params.fee_account, units=fee))
    return AddTransaction(
        transaction=TransactionInput(date=params.date, narration=params.narration or f"Buy {params.commodity}", postings=postings)
    )


class SellParams(TradeParams):
    gains_account: AccountName | None = Field(
        default=None, description="Where profit or loss is booked. Defaults to the account's configured gains account."
    )
    lot_cost: FiniteDecimal | None = Field(
        default=None, description="Per-unit purchase cost, to pick a lot when the holding has several."
    )
    lot_date: dt.date | None = Field(default=None, description="Purchase date of the lot, to pick it.")


def compile_sell(params: SellParams, context: RecipeContext) -> Operation:
    cash = _cash_account(params.cash_account, context)
    gains = params.gains_account or context.profile.gains_account
    if gains is None:
        raise RecipeError("no gains account given and the account has none configured")
    context.require_open(gains)
    units, price, total = _trade_amounts(params, cash, context)
    fee = _fee(params, total.currency, context)
    received = total.number - (fee.number if fee else Decimal(0))
    lot = Cost(number=params.lot_cost, currency=price.currency if params.lot_cost is not None else None, date=params.lot_date)
    postings = [
        Posting(
            account=context.account,
            units=Amount(number=-units, currency=params.commodity),
            cost=lot,
            price=price,
        ),
        Posting(account=cash, units=Amount(number=received, currency=total.currency)),
    ]
    if fee:
        postings.append(Posting(account=params.fee_account, units=fee))
    postings.append(Posting(account=gains))
    return AddTransaction(
        transaction=TransactionInput(date=params.date, narration=params.narration or f"Sell {params.commodity}", postings=postings)
    )


class DividendParams(DatedParams):
    amount: Money = Field(description="Cash received, after any tax.")
    income_account: AccountName
    cash_account: AccountName | None = None
    tax_withheld: Money | None = None
    tax_account: AccountName | None = None
    narration: Text = "Dividend"


def compile_dividend(params: DividendParams, context: RecipeContext) -> Operation:
    cash = _cash_account(params.cash_account, context)
    context.require_open(params.income_account)
    net = amount_of(params.amount, context.currencies(cash), "amount")
    gross = net.number
    postings = [Posting(account=cash, units=net)]
    if params.tax_withheld is not None:
        if params.tax_account is None:
            raise RecipeError("tax_account is required when tax is withheld")
        context.require_open(params.tax_account)
        tax = amount_of(params.tax_withheld, [net.currency], "tax_withheld")
        postings.append(Posting(account=params.tax_account, units=tax))
        gross += tax.number
    postings.append(Posting(account=params.income_account, units=Amount(number=-gross, currency=net.currency)))
    return AddTransaction(transaction=TransactionInput(date=params.date, narration=params.narration, postings=postings))


def register(registry: RecipeRegistry) -> None:
    kinds = frozenset({KIND})
    registry.describe_kind("brokerage", "Investments held as commodities, with a cash account for settlement.")
    registry.register(Recipe("buy", "Buy", "Buy units of a commodity. Give the price per unit or the total.", kinds, TradeParams, compile_buy))
    registry.register(Recipe("sell", "Sell", "Sell units, booking profit or loss to the gains account.", kinds, SellParams, compile_sell))
    registry.register(Recipe("dividend", "Dividend", "Dividend or distribution paid to the cash account.", kinds, DividendParams, compile_dividend))
