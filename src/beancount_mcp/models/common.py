import re
from decimal import Decimal
from typing import Annotated

from beancount_mcp.amounts import parse_amount, parse_number, parse_rate
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, StringConstraints, model_validator

ACCOUNT_PATTERN = r"^(Assets|Liabilities|Equity|Income|Expenses)(:[A-Z0-9][A-Za-z0-9-]*)+$"
CURRENCY_PATTERN = r"^([A-Z]|[A-Z][A-Z0-9'._-]{0,22}[A-Z0-9])$"
TAG_PATTERN = r"^[A-Za-z0-9_/.-]+$"
META_KEY_PATTERN = r"^[a-z][a-zA-Z0-9_-]*$"

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _reject_control_chars(value: str) -> str:
    if _CONTROL_CHARS.search(value):
        raise ValueError("control characters are not allowed")
    return value


Text = Annotated[str, AfterValidator(_reject_control_chars)]
AccountName = Annotated[str, StringConstraints(pattern=ACCOUNT_PATTERN)]
CurrencyCode = Annotated[str, StringConstraints(pattern=CURRENCY_PATTERN)]
Tag = Annotated[str, StringConstraints(pattern=TAG_PATTERN)]
MetaKey = Annotated[str, StringConstraints(pattern=META_KEY_PATTERN)]
FiniteDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]


def _formula(value):
    """A string is a number or a formula such as `18.65 + 6.60 + 7.40`, worked out exactly here and not by the caller."""
    return parse_number(value) if isinstance(value, str) else value


Number = Annotated[Decimal, BeforeValidator(_formula), Field(allow_inf_nan=False)]
"""A number that may be written as a formula. Used where a caller would otherwise add up or convert in its head."""

RATE_PLACES = 8


def _rate_formula(value):
    """A rate keeps eight places, so `1 / 8.73` is a usable rate and not 0.11."""
    return parse_rate(value) if isinstance(value, str) else value


Rate = Annotated[Decimal, BeforeValidator(_rate_formula), Field(allow_inf_nan=False)]
"""An exchange rate, which may be a formula such as `1 / 8.73`."""


class Amount(BaseModel):
    """A number and a currency. Also accepted as text: "12.50 USD", or a formula: "18.65 + 6.60 + 7.40 GBP"."""

    number: FiniteDecimal
    currency: CurrencyCode

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, value):
        if not isinstance(value, str):
            return value
        number, currency = parse_amount(value)
        return {"number": number, "currency": currency}
