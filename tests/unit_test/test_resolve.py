from datetime import date

import pytest

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AccountInfo
from beancount_mcp.services.resolve import resolve_account, resolve_params


def accounts():
    names = {
        "Assets:Bank:Checking": "Everyday account",
        "Assets:Bank:Savings": None,
        "Assets:Cash": None,
        "Expenses:Food": None,
        "Income:Food": None,
        "Liabilities:Card:Main": "Main dual-currency card",
    }
    result = [AccountInfo(name=n, open_date=date(2026, 1, 1), description=d) for n, d in names.items()]
    result.append(AccountInfo(name="Assets:Old", open_date=date(2020, 1, 1), close_date=date(2021, 1, 1)))
    return result


@pytest.mark.parametrize("query,expected", [
    ("Assets:Cash", "Assets:Cash"),
    ("assets:cash", "Assets:Cash"),
    ("Checking", "Assets:Bank:Checking"),
    ("Bank:Savings", "Assets:Bank:Savings"),
    ("everyday", "Assets:Bank:Checking"),
    ("card main", "Liabilities:Card:Main"),
    ("  cash ", "Assets:Cash"),
])
def test_unique_matches(query, expected):
    assert resolve_account(accounts(), query) == expected


def test_roots_break_ties_and_fall_back():
    assert resolve_account(accounts(), "food", ("Expenses",)) == "Expenses:Food"
    assert resolve_account(accounts(), "cash", ("Expenses",)) == "Assets:Cash"
    with pytest.raises(RecipeError, match="several accounts"):
        resolve_account(accounts(), "food")


def test_closed_accounts_never_match():
    with pytest.raises(RecipeError, match="no open account"):
        resolve_account(accounts(), "Old")


def test_unknown_names_suggest_close_ones():
    with pytest.raises(RecipeError, match="Did you mean Assets:Bank:Checking"):
        resolve_account(accounts(), "Assets:Bank:Chekcing")
    with pytest.raises(RecipeError, match="list_accounts"):
        resolve_account(accounts(), "zzzzzz")


def test_recipe_params_are_resolved_deeply_and_other_values_untouched():
    params = {"income_account": "food", "amount": "5 USD", "fees": [{"account": "cash", "amount": "1"}],
              "tags": ["cash"], "payee": "cash"}
    resolved = resolve_params(accounts(), params)
    assert resolved["income_account"] == "Income:Food"
    assert resolved["fees"][0]["account"] == "Assets:Cash"
    assert resolved["tags"] == ["cash"] and resolved["payee"] == "cash" and resolved["amount"] == "5 USD"
