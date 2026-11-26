"""Input leniency shared by recipes.

Agents fail on avoidable details, so recipes accept the loosest unambiguous input
and do the arithmetic here: a bare number where the account has one currency,
either of two related amounts, a rate instead of a converted amount, and a
default date of today.
"""

import datetime as dt
import hashlib
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal

from pydantic import BaseModel, Field

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import Posting
from beancount_mcp.models.common import AccountName, Amount, FiniteDecimal

Money = Amount | FiniteDecimal
"""An amount, text like "12.50 USD", or a bare number when the currency is unambiguous."""

RATE_DESCRIPTION = "Units of the other amount's currency per one unit of this one. Use instead of giving the other amount."


def today() -> dt.date:
    return dt.date.today()


def amount_of(value: Money, currencies: Sequence[str], label: str) -> Amount:
    """A positive amount. The sign is ignored, because each recipe knows the direction."""
    if isinstance(value, Amount):
        amount = value
    elif len(currencies) == 1:
        amount = Amount(number=value, currency=currencies[0])
    else:
        raise RecipeError(f'{label}: give the currency too, for example "{value} USD"')
    if amount.number == 0:
        raise RecipeError(f"{label} must not be zero")
    return Amount(number=abs(amount.number), currency=amount.currency)


def negated(amount: Amount) -> Amount:
    return Amount(number=-amount.number, currency=amount.currency)


def exchange(
    base: Amount,
    other: Money | None,
    rate: Decimal | None,
    other_currencies: Sequence[str],
    label: str,
) -> Amount:
    """The amount on the other side of an exchange from `base`.

    Taken from `other` when given, else computed from `rate`. With neither, the
    other side is the same amount, which needs its account to hold that currency.
    """
    if other is not None:
        result = amount_of(other, other_currencies, label)
    elif rate is not None:
        if len(other_currencies) != 1:
            raise RecipeError(f"{label}: give the amount with its currency, a rate alone is ambiguous")
        if rate <= 0:
            raise RecipeError("rate must be positive")
        number = (base.number * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        result = Amount(number=number, currency=other_currencies[0])
    elif not other_currencies or base.currency in other_currencies:
        return base
    else:
        raise RecipeError(f"{label}: {base.currency} differs from the account's {', '.join(other_currencies)}; give the amount or a rate")
    if result.currency == base.currency and result.number != base.number:
        raise RecipeError(f"{label}: the same currency must be the same amount")
    return result


def two_legs(
    base_account: str,
    base: Amount,
    other_account: str,
    other: Amount,
    base_sign: int,
) -> list[Posting]:
    """Postings moving `base` on one account against `other` on another.

    `base_sign` is the sign of the base posting. When currencies differ, the price
    on the base posting makes the two sides balance exactly.
    """
    price = None
    if base.currency != other.currency:
        price = Amount(number=other.number / base.number, currency=other.currency)
    return [
        Posting(account=base_account, units=Amount(number=base_sign * base.number, currency=base.currency), price=price),
        Posting(account=other_account, units=Amount(number=-base_sign * other.number, currency=other.currency)),
    ]


class Split(BaseModel):
    """An extra amount booked to another account, such as a fee or a tax."""

    account: AccountName
    amount: Money


def auto_link(prefix: str, *parts: object) -> str:
    """A stable link name, so recipes that open an item need no identifier from the caller."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:6]
    return f"{prefix}-{digest}"


class DatedParams(BaseModel):
    date: dt.date = Field(default_factory=today, description="Defaults to today.")
