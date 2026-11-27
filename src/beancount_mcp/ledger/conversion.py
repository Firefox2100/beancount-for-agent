"""Counting amounts in several currencies as one, at today's rate, for references such as budgets and goals."""

from decimal import Decimal

from beancount_mcp.models.conversion import Converted

Rates = dict[str, tuple[Decimal, str]]


def money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def counted(totals: dict[str, Decimal], currency: str, rates: Rates) -> tuple[Decimal, list[Converted], dict[str, Decimal]]:
    """What counts in `currency`: its own amount plus other currencies that have a rate, and the rest unconverted."""
    used = totals.get(currency, Decimal(0))
    converted, left = [], {}
    for other, amount in sorted(totals.items()):
        if other == currency or amount == 0:
            continue
        if other in rates:
            rate, source = rates[other]
            used += amount * rate
            converted.append(Converted(currency=other, amount=money(amount), rate=format(rate.normalize(), "f"), value=money(amount * rate), source=source))  # type: ignore[arg-type]
        else:
            left[other] = amount
    return used, converted, left
