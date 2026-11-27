"""Amounts written as text: `12.50 USD`, `USD 1,200`, and formulas such as `18.65 + 6.60 + 7.40 GBP`.

The arithmetic is `calc.py`. This layer only finds the currency, which may stand once anywhere in the text or be
repeated identically, and refuses two different currencies in one formula.
"""

import re
from decimal import Decimal

from beancount_mcp.calc import CalcError, evaluate

# A currency code stands apart from numbers and operators: `12GBP` and `1E5` are not read as a currency.
_CURRENCY = re.compile(r"(?<![\w.,])[A-Z][A-Z0-9'._-]*(?![\w.,])")


def split_currency(text: str) -> tuple[str, str | None]:
    """The text without its currency code, and the code. `ValueError` when the text names two currencies."""
    codes = _CURRENCY.findall(text)
    if len(set(codes)) > 1:
        raise ValueError(f'one formula cannot mix currencies ({", ".join(sorted(set(codes)))}): convert first, or give each amount on its own')
    return (_CURRENCY.sub(" ", text), codes[0] if codes else None)


def parse_amount(text: str) -> tuple[Decimal, str]:
    """A number and its currency from `12.50 USD`, `USD 1,200` or a formula with a currency in it."""
    stripped, currency = split_currency(text)
    if currency is None:
        raise ValueError('expected an amount like "12.50 USD", or a formula like "18.65 + 6.60 GBP"')
    return parse_number(stripped), currency


def parse_number(text: str) -> Decimal:
    """A number or a formula, as an exact decimal."""
    try:
        return evaluate(text).value
    except CalcError as error:
        raise ValueError(str(error)) from None


def parse_rate(text: str) -> Decimal:
    """A rate or a formula for one, with up to eight decimal places and no trailing zeros."""
    try:
        value = evaluate(text, minimum_places=8).value
    except CalcError as error:
        raise ValueError(str(error)) from None
    return Decimal(format(value.normalize(), "f"))
