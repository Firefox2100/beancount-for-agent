import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from beancount_mcp.ledger.goals import months_between, status
from beancount_mcp.models.common import Amount
from beancount_mcp.models.goals import Goal

D = dt.date.fromisoformat
BALANCES = {"Assets:Savings:Holiday": {"GBP": Decimal("600")}, "Assets:Savings:Other": {"GBP": Decimal("50")}, "Assets:Bank": {"GBP": Decimal("999")}}


def goal(**overrides) -> Goal:
    values = dict(title="Holiday", accounts=["Assets:Savings:Holiday"], target=Amount(number=Decimal("1000"), currency="GBP"))
    return Goal(**{**values, **overrides})


def test_a_goal_counts_assets_only():
    with pytest.raises(ValidationError, match="under Assets"):
        goal(accounts=["Expenses:Food"])
    with pytest.raises(ValidationError):
        goal(accounts=[])


def test_months_are_whole_and_never_negative():
    assert months_between(D("2026-03-10"), D("2026-09-10")) == 6
    assert months_between(D("2026-03-10"), D("2026-09-09")) == 5
    assert months_between(D("2026-03-10"), D("2026-03-01")) == 0
    assert months_between(D("2026-03-10"), D("2025-01-01")) == 0


def test_saved_remaining_percent_and_the_group_prefix():
    result = status("holiday", goal(accounts=["Assets:Savings"]), BALANCES, D("2026-03-10"))
    assert (result.saved, result.remaining, result.percent, result.state, result.reached) == ("650.00", "350.00", "65.00", "open", False)
    assert status("h", goal(), BALANCES, D("2026-03-10")).saved == "600.00"


def test_a_deadline_gives_the_monthly_amount_needed():
    result = status("h", goal(by=D("2026-09-10")), BALANCES, D("2026-03-10"))
    assert result.months_left == 6 and result.needed_monthly == "66.67" and result.state == "open"


def test_a_plan_decides_on_track_or_behind_and_gives_the_finish():
    on = status("h", goal(by=D("2026-09-10"), monthly=Amount(number=Decimal("100"), currency="GBP")), BALANCES, D("2026-03-10"))
    assert on.state == "on_track" and on.projected == D("2026-07-10")
    behind = status("h", goal(by=D("2026-05-10"), monthly=Amount(number=Decimal("100"), currency="GBP")), BALANCES, D("2026-03-10"))
    assert behind.state == "behind" and behind.projected == D("2026-07-10")


def test_a_missed_deadline_without_a_plan_is_behind():
    assert status("h", goal(by=D("2026-01-01")), BALANCES, D("2026-03-10")).state == "behind"


def test_reaching_the_target_stops_the_arithmetic():
    result = status("h", goal(target=Amount(number=Decimal("500"), currency="GBP"), by=D("2026-09-10")), BALANCES, D("2026-03-10"))
    assert result.reached and result.state == "reached" and result.remaining == "0.00" and result.needed_monthly is None and result.percent == "100.00"


def test_other_currencies_are_converted_when_there_is_a_rate_and_listed_when_there_is_not():
    balances = {"Assets:Savings:Holiday": {"GBP": Decimal("100"), "EUR": Decimal("200"), "CNY": Decimal("500")}}
    result = status("h", goal(), balances, D("2026-03-10"), {"EUR": (Decimal("0.85"), "reference")})
    assert result.saved == "270.00" and result.approximate and result.other_currencies == {"CNY": "500.00"}
    assert result.converted[0].value == "170.00" and result.converted[0].source == "reference"
