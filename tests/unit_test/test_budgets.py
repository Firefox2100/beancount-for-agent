import datetime as dt
from decimal import Decimal

import pytest
from beancount import loader
from pydantic import ValidationError

from beancount_mcp.ledger.budgets import period_of, status, suggest
from beancount_mcp.models.budgets import Budget
from beancount_mcp.models.common import Amount

D = dt.date.fromisoformat


def budget(limit="300", **overrides) -> Budget:
    values = dict(account="Expenses:Food", amount=Amount(number=Decimal(limit), currency="GBP"))
    return Budget(**{**values, **overrides})


def ledger(*spends):
    lines = ["2025-01-01 open Assets:Bank", "2025-01-01 open Expenses:Food:Groceries", "2025-01-01 open Expenses:Food:Restaurants",
             "2025-01-01 open Expenses:Rent", "2025-01-01 open Expenses:Fun"]
    for day, account, amount, *currency in spends:
        lines += [f'{day} * "x"', f"  {account}  {amount} {currency[0] if currency else 'GBP'}", f"  Assets:Bank  -{amount} {currency[0] if currency else 'GBP'}"]
    return loader.load_string("\n".join(lines))[0]


def test_budget_must_limit_expenses():
    with pytest.raises(ValidationError, match="under Expenses"):
        budget(account="Assets:Bank")
    with pytest.raises(ValidationError):
        budget(start_day=29)


@pytest.mark.parametrize("budget_kwargs,day,expected", [
    ({}, "2026-02-17", ("2026-02-01", "2026-02-28")),
    ({"start_day": 25}, "2026-02-17", ("2026-01-25", "2026-02-24")),
    ({"start_day": 25}, "2026-02-25", ("2026-02-25", "2026-03-24")),
    ({"start_day": 25}, "2026-01-10", ("2025-12-25", "2026-01-24")),
    ({"every": "week"}, "2026-02-17", ("2026-02-16", "2026-02-22")),
    ({"every": "year"}, "2026-02-17", ("2026-01-01", "2026-12-31")),
])
def test_periods(budget_kwargs, day, expected):
    assert period_of(budget(**budget_kwargs), D(day)) == (D(expected[0]), D(expected[1]))


def test_spending_on_pace_is_ok_and_the_numbers_are_worked_out():
    entries = ledger(("2026-02-03", "Expenses:Food:Groceries", "60"), ("2026-02-09", "Expenses:Food:Restaurants", "40"))
    result = status("food", budget(), entries, D("2026-02-14"))
    assert (result.spent, result.remaining, result.used_percent, result.state) == ("100.00", "200.00", "33.33", "ok")
    assert (result.start, result.end, result.days_left, result.title) == (D("2026-02-01"), D("2026-02-28"), 14, "Food")
    assert result.projected == "200.00" and result.daily_allowance == "14.29"


def test_spending_faster_than_the_period_is_ahead_and_past_the_limit_is_over():
    entries = ledger(("2026-02-03", "Expenses:Food:Groceries", "200"))
    assert status("food", budget(), entries, D("2026-02-10")).state == "ahead"
    over = status("food", budget("150"), entries, D("2026-02-10"))
    assert over.state == "over" and over.remaining == "-50.00" and over.daily_allowance is None


def test_other_currencies_are_listed_not_counted_and_unrelated_spending_is_ignored():
    entries = ledger(("2026-02-03", "Expenses:Food:Groceries", "20"), ("2026-02-04", "Expenses:Food:Restaurants", "15", "EUR"), ("2026-02-05", "Expenses:Rent", "900"))
    result = status("food", budget(), entries, D("2026-02-10"))
    assert result.spent == "20.00" and result.other_currencies == {"EUR": "15.00"}


def test_history_lists_the_earlier_periods_with_which_went_over():
    entries = ledger(("2026-01-05", "Expenses:Food:Groceries", "350"), ("2025-12-05", "Expenses:Food:Groceries", "100"))
    history = status("food", budget(), entries, D("2026-02-10")).history
    assert [(h.start.isoformat(), h.spent, h.over) for h in history] == [("2026-01-01", "350.00", True), ("2025-12-01", "100.00", False), ("2025-11-01", "0.00", False)]


def test_a_budget_on_a_single_account_counts_just_that_account():
    entries = ledger(("2026-02-03", "Expenses:Food:Groceries", "50"), ("2026-02-04", "Expenses:Food:Restaurants", "30"))
    assert status("g", budget(account="Expenses:Food:Groceries"), entries, D("2026-02-10")).spent == "50.00"


def test_suggestions_average_recent_whole_months_round_up_and_skip_covered_groups():
    entries = ledger(
        ("2025-12-05", "Expenses:Food:Groceries", "250"), ("2026-01-05", "Expenses:Food:Groceries", "280"), ("2026-02-05", "Expenses:Food:Groceries", "232"),
        ("2025-12-06", "Expenses:Rent", "1000"), ("2026-01-06", "Expenses:Rent", "1000"), ("2026-02-06", "Expenses:Rent", "1000"),
        ("2026-02-10", "Expenses:Fun", "40"),
        ("2026-03-03", "Expenses:Fun", "500"),
    )
    found = suggest(entries, {}, D("2026-03-10"))
    by_id = {s.id: s for s in found}
    assert set(by_id) == {"food", "rent"}
    assert by_id["food"].average == "254.00" and by_id["food"].budget.amount.number == Decimal(260) and by_id["food"].months == 3
    assert by_id["rent"].budget.amount.number == Decimal(1000)
    covered = suggest(entries, {"mine": budget(account="Expenses:Food:Groceries")}, D("2026-03-10"))
    assert [s.id for s in covered] == ["rent"]


def test_other_currencies_with_a_rate_are_converted_and_marked_approximate():
    entries = ledger(("2026-02-03", "Expenses:Food:Groceries", "100"), ("2026-02-04", "Expenses:Food:Restaurants", "20", "EUR"), ("2026-02-05", "Expenses:Food:Groceries", "50", "CNY"))
    result = status("food", budget(), entries, D("2026-02-10"), {"EUR": (Decimal("0.85"), "reference")})
    assert result.spent == "117.00" and result.approximate and result.remaining == "183.00"
    (converted,) = result.converted
    assert (converted.currency, converted.amount, converted.rate, converted.value, converted.source) == ("EUR", "20.00", "0.85", "17.00", "reference")
    assert result.other_currencies == {"CNY": "50.00"}


def test_without_any_rate_nothing_is_converted_and_the_status_is_exact():
    entries = ledger(("2026-02-04", "Expenses:Food:Restaurants", "20", "EUR"))
    result = status("food", budget(), entries, D("2026-02-10"), {})
    assert result.spent == "0.00" and not result.approximate and result.converted == [] and result.other_currencies == {"EUR": "20.00"}


def test_conversion_counts_towards_state_projection_and_history():
    entries = ledger(("2026-02-03", "Expenses:Food:Groceries", "100", "EUR"), ("2026-01-05", "Expenses:Food:Groceries", "400", "EUR"))
    result = status("food", budget("100"), entries, D("2026-02-10"), {"EUR": (Decimal("2"), "ledger")})
    assert result.spent == "200.00" and result.state == "over" and result.converted[0].source == "ledger"
    assert result.history[0].spent == "800.00" and result.history[0].over
