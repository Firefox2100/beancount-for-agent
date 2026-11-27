from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from beancount_mcp.amounts import parse_amount, parse_rate, split_currency
from beancount_mcp.models.common import Amount, Number, Rate
from beancount_mcp.recipes.helpers import Money


class Holder(BaseModel):
    money: Money
    rate: Rate | None = None
    number: Number | None = None


@pytest.mark.parametrize("text,number,currency", [
    ("12.50 USD", "12.50", "USD"),
    ("USD 1,200", "1200", "USD"),
    ("18.65 + 6.60 + 7.40 GBP", "32.65", "GBP"),
    ("GBP 18.65 + 6.60", "25.25", "GBP"),
    ("(100 - 15) / 2 GBP", "42.50", "GBP"),
    ("10 GBP + 5 GBP", "15.00", "GBP"),
    ("48 / 3 CNY", "16.00", "CNY"),
])
def test_amount_text_may_be_a_formula_with_the_currency_anywhere(text, number, currency):
    assert parse_amount(text) == (Decimal(number), currency)
    assert Amount.model_validate(text) == Amount(number=Decimal(number), currency=currency)


@pytest.mark.parametrize("text,fragment", [
    ("10 GBP + 5 USD", "cannot mix currencies"),
    ("12.50", "expected an amount"),
    ("12GBP", "expected an amount"),
    ("1E5 USD", 'cannot read "E"'),
    ("10 / 0 GBP", "division by zero"),
    ("2 ** 3 GBP", "number was expected"),
])
def test_amount_text_that_is_not_one_says_what_to_send(text, fragment):
    with pytest.raises(ValidationError, match=fragment):
        Amount.model_validate(text)


def test_currency_is_found_only_where_it_stands_apart():
    assert split_currency("12 GBP")[1] == "GBP"
    assert split_currency("(12 + 3) GBP")[1] == "GBP"
    assert split_currency("12GBP")[1] is None
    assert split_currency("12 + 3")[1] is None


def test_money_takes_an_amount_a_formula_with_currency_or_a_bare_number_or_formula():
    assert Holder(money="18.65 + 6.60 GBP").money == Amount(number=Decimal("25.25"), currency="GBP")
    assert Holder(money={"number": "5", "currency": "USD"}).money == Amount(number=Decimal("5"), currency="USD")
    assert Holder(money="10 + 5").money == Decimal("15.00")
    assert Holder(money=12.5).money == Decimal("12.5")
    assert Holder(money="12.5").money == Decimal("12.5")


def test_a_rate_keeps_eight_places_and_no_trailing_zeros():
    assert parse_rate("1 / 8.73") == Decimal("0.11454754")
    assert parse_rate("8") == Decimal("8")
    assert parse_rate("0.1145") == Decimal("0.1145")
    assert Holder(money="1 GBP", rate="1/8.73").rate == Decimal("0.11454754")
    assert Holder(money="1 GBP", rate=0.125).rate == Decimal("0.125")
    with pytest.raises(ValidationError, match="division by zero"):
        Holder(money="1 GBP", rate="1/0")


def test_a_number_field_does_not_round_a_plain_number():
    assert Holder(money="1 GBP", number="12.345").number == Decimal("12.345")
    assert Holder(money="1 GBP", number="12.345 * 2").number == Decimal("24.690")
