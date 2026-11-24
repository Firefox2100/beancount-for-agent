from datetime import date
from decimal import Decimal

import pytest
from pydantic import BaseModel

from beancount_mcp.ledger.errors import RecipeError, RecipeNotFound
from beancount_mcp.models import AccountInfo, AccountProfile, Batch
from beancount_mcp.recipes import default_registry
from beancount_mcp.recipes.base import Recipe, RecipeContext
from beancount_mcp.recipes.credit_card import (
    CloseStatementParams,
    PayCardParams,
    PurchaseParams,
    compile_close_statement,
    compile_pay_card,
    compile_purchase,
)
from beancount_mcp.recipes.registry import RecipeRegistry

CARD = "Liabilities:Card:Main"
UNBILLED = CARD + ":Unbilled"


def context(balances=None, profile=None, closed=()):
    accounts = {
        CARD: AccountInfo(name=CARD, open_date=date(2026, 1, 1), currencies=["USD", "CNY"], type="credit_card"),
        UNBILLED: AccountInfo(name=UNBILLED, open_date=date(2026, 1, 1)),
        "Expenses:Food": AccountInfo(name="Expenses:Food", open_date=date(2026, 1, 1)),
        "Assets:Debit": AccountInfo(name="Assets:Debit", open_date=date(2026, 1, 1), currencies=["CNY"]),
    }
    for name in closed:
        accounts[name].close_date = date(2026, 1, 2)
    balances = balances or {}
    return RecipeContext(
        account=CARD,
        kind="credit_card",
        profile=profile or AccountProfile(),
        accounts=accounts,
        balance=lambda name: {k: Decimal(v) for k, v in balances.get(name, {}).items()},
    )


def amount(number, currency):
    return {"number": number, "currency": currency}


def purchase(**fields):
    return PurchaseParams.model_validate(
        {"date": "2026-02-01", "expense_account": "Expenses:Food", **fields}
    )


def postings(operation):
    return [(p.account, str(p.units.number), p.units.currency) for p in operation.transaction.postings]


def test_billing_currency_purchase_hits_the_card():
    operation = compile_purchase(purchase(amount=amount("50", "CNY")), context())
    assert postings(operation) == [("Expenses:Food", "50", "CNY"), (CARD, "-50", "CNY")]


def test_foreign_purchase_goes_to_unbilled():
    operation = compile_purchase(purchase(amount=amount("100", "GBP")), context())
    assert postings(operation)[1] == (UNBILLED, "-100", "GBP")


def test_converted_purchase_records_original_amount():
    operation = compile_purchase(
        purchase(amount=amount("20", "GBP"), billed_amount=amount("26", "USD")), context()
    )
    assert postings(operation) == [("Expenses:Food", "26", "USD"), (CARD, "-26", "USD")]
    assert operation.transaction.meta == {"original-amount": "20 GBP"}


def test_purchase_validation():
    with pytest.raises(RecipeError):
        compile_purchase(purchase(amount=amount("0", "USD")), context())
    with pytest.raises(RecipeError):
        compile_purchase(purchase(amount=amount("10", "GBP"), billed_amount=amount("9", "EUR")), context())
    with pytest.raises(RecipeError, match="not open"):
        compile_purchase(purchase(amount=amount("10", "GBP")), context(closed=[UNBILLED]))


def close(**fields):
    return CloseStatementParams.model_validate({"date": "2026-03-01", **fields})


def test_close_statement_uses_unit_price_that_balances():
    params = close(conversions=[{"unbilled": amount("100", "GBP"), "billed": amount("130.37", "USD")}])
    operation = compile_close_statement(params, context({UNBILLED: {"GBP": "-100"}}))
    first, second = operation.transaction.postings
    assert first.units.number * first.price.number == Decimal("130.37")
    assert second.units.number == Decimal("-130.37")


def test_close_statement_with_balances_becomes_batch():
    params = close(
        conversions=[{"unbilled": amount("100", "GBP"), "billed": amount("130", "USD")}],
        statement_balances=[amount("130", "USD")],
    )
    operation = compile_close_statement(params, context({UNBILLED: {"GBP": "-100"}}))
    assert isinstance(operation, Batch)
    assertion = operation.operations[1].directive
    assert assertion.date == date(2026, 3, 2) and assertion.amount.number == Decimal("-130")


def test_close_statement_limits():
    params = close(conversions=[{"unbilled": amount("100", "GBP"), "billed": amount("130", "USD")}])
    with pytest.raises(RecipeError, match="unbilled"):
        compile_close_statement(params, context({UNBILLED: {"GBP": "-99"}}))
    same = close(conversions=[{"unbilled": amount("1", "USD"), "billed": amount("1", "USD")}])
    with pytest.raises(RecipeError, match="different"):
        compile_close_statement(same, context({UNBILLED: {"USD": "-1"}}))


def pay(**fields):
    return PayCardParams.model_validate({"date": "2026-03-10", **fields})


def test_cross_currency_payment_carries_price():
    params = pay(
        from_account="Assets:Debit",
        payments=[{"paid": amount("720", "CNY"), "cleared": amount("100", "USD")}],
    )
    source, card = compile_pay_card(params, context()).transaction.postings
    assert source.units.number == Decimal("-720") and card.units.number == Decimal("100")
    assert card.price.number == Decimal("7.2") and card.price.currency == "CNY"


def test_payment_needs_a_source_and_exact_same_currency_amounts():
    both = [{"paid": amount("50", "CNY"), "cleared": amount("50", "CNY")}]
    with pytest.raises(RecipeError, match="autopay"):
        compile_pay_card(pay(payments=both), context())
    assert compile_pay_card(pay(payments=both), context(profile=AccountProfile(autopay_from="Assets:Debit")))
    uneven = [{"paid": amount("49", "CNY"), "cleared": amount("50", "CNY")}]
    with pytest.raises(RecipeError, match="same amount"):
        compile_pay_card(pay(from_account="Assets:Debit", payments=uneven), context())


class Empty(BaseModel):
    pass


def noop_recipe(recipe_id="custom", kinds=("thing",)):
    return Recipe(recipe_id, "Custom", "", frozenset(kinds), Empty, lambda params, ctx: None)


def test_registry_filters_by_kind_and_allow_list():
    registry = default_registry(load_plugins=False)
    registry.register(noop_recipe())
    assert [r.id for r in registry.for_kind("thing")] == ["custom"]
    assert [r.id for r in registry.for_kind("credit_card", ["purchase"])] == ["purchase"]
    assert registry.for_kind(None) == []
    with pytest.raises(RecipeNotFound):
        registry.get("missing")


def test_duplicate_registration_rejected():
    registry = RecipeRegistry()
    registry.register(noop_recipe())
    with pytest.raises(ValueError):
        registry.register(noop_recipe())


def test_plugins_register_through_entry_points():
    class Point:
        def load(self):
            return lambda registry: registry.register(noop_recipe("from_plugin"))

    registry = RecipeRegistry()
    registry.load_plugins([Point()])
    assert registry.get("from_plugin").title == "Custom"
