import re
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

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


class Amount(BaseModel):
    number: FiniteDecimal
    currency: CurrencyCode
