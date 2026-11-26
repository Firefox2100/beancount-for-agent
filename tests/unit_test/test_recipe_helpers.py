from decimal import Decimal

import pytest

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models.common import Amount
from beancount_mcp.recipes.helpers import amount_of, auto_link, exchange


def usd(number):
    return Amount(number=Decimal(number), currency="USD")


def test_amount_text_forms():
    assert Amount.model_validate("12.50 USD") == usd("12.50")
    assert Amount.model_validate("USD 1,200") == usd("1200")
    with pytest.raises(ValueError):
        Amount.model_validate("twelve")


def test_bare_number_takes_the_only_currency():
    assert amount_of(Decimal("5"), ["USD"], "x") == usd("5")
    with pytest.raises(RecipeError, match="currency"):
        amount_of(Decimal("5"), ["USD", "CNY"], "x")
    with pytest.raises(RecipeError, match="zero"):
        amount_of(usd("0"), [], "x")


def test_sign_is_ignored():
    assert amount_of(usd("-3"), [], "x") == usd("3")


def test_exchange_uses_the_given_amount_first():
    assert exchange(usd("10"), Amount(number=Decimal("72"), currency="CNY"), None, ["CNY"], "x").number == 72


def test_exchange_from_rate_needs_one_target_currency():
    assert exchange(usd("10"), None, Decimal("7.25"), ["CNY"], "x") == Amount(number=Decimal("72.50"), currency="CNY")
    with pytest.raises(RecipeError, match="ambiguous"):
        exchange(usd("10"), None, Decimal("7.25"), ["CNY", "GBP"], "x")


def test_exchange_without_conversion_needs_the_currency_to_fit():
    assert exchange(usd("10"), None, None, ["USD", "CNY"], "x") == usd("10")
    assert exchange(usd("10"), None, None, [], "x") == usd("10")
    with pytest.raises(RecipeError, match="rate"):
        exchange(usd("10"), None, None, ["CNY"], "x")


def test_same_currency_must_match():
    with pytest.raises(RecipeError, match="same amount"):
        exchange(usd("10"), usd("11"), None, ["USD"], "x")


def test_auto_link_is_stable_and_distinct():
    assert auto_link("claim", "a", 1) == "claim-df4504"
    assert auto_link("claim", "a", 1) != auto_link("claim", "a", 2)
