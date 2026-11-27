import datetime as dt

from beancount import loader

from beancount_mcp.ledger.reports import income_statement

D = dt.date.fromisoformat

LEDGER = """
2025-01-01 open Assets:Bank
2025-01-01 open Income:Salary
2025-01-01 open Income:Interest
2025-01-01 open Expenses:Food:Groceries
2025-01-01 open Expenses:Food:Restaurants
2025-01-01 open Expenses:Rent
2025-01-01 open Equity:Opening

2026-01-02 * "Pay"
  Assets:Bank          3000.00 GBP
  Income:Salary       -3000.00 GBP
2026-01-03 * "Rent"
  Expenses:Rent         1000.00 GBP
  Assets:Bank          -1000.00 GBP
2026-01-10 * "Shop"
  Expenses:Food:Groceries  80.00 GBP
  Assets:Bank             -80.00 GBP
2026-02-02 * "Pay"
  Assets:Bank          3000.00 GBP
  Income:Salary       -3000.00 GBP
2026-02-04 * "Dinner"
  Expenses:Food:Restaurants  60.00 GBP
  Assets:Bank               -60.00 GBP
2026-02-05 * "Shop"
  Expenses:Food:Groceries  100.00 GBP
  Assets:Bank             -100.00 GBP
2026-02-06 * "Refund"
  Expenses:Food:Groceries  -10.00 GBP
  Assets:Bank               10.00 GBP
2026-02-07 * "Opening move"
  Assets:Bank   500.00 GBP
  Equity:Opening  -500.00 GBP
"""
ENTRIES = loader.load_string(LEDGER)[0]


def run(start, end, depth=2, prefix=None, interval=None, compare=False):
    return income_statement(ENTRIES, "main", D(start), D(end), depth, prefix, interval, compare)


def rows(items):
    return {r.account: r.totals for r in items}


def test_totals_are_by_account_with_expenses_and_income_positive_and_equity_ignored():
    report = run("2026-02-01", "2026-02-28")
    assert rows(report.income) == {"Income:Salary": {"GBP": "3000.00"}}
    assert rows(report.expenses) == {"Expenses:Food": {"GBP": "150.00"}}
    assert report.income_total == {"GBP": "3000.00"} and report.expense_total == {"GBP": "150.00"} and report.net == {"GBP": "2850.00"}
    assert report.savings_rate == "95.0"


def test_depth_and_a_group_drill_down():
    deep = run("2026-02-01", "2026-02-28", depth=3)
    assert rows(deep.expenses) == {"Expenses:Food:Groceries": {"GBP": "90.00"}, "Expenses:Food:Restaurants": {"GBP": "60.00"}}
    assert [r.account for r in deep.expenses] == ["Expenses:Food:Groceries", "Expenses:Food:Restaurants"]
    drill = run("2026-01-01", "2026-02-28", depth=3, prefix="Expenses:Food")
    assert rows(drill.expenses)["Expenses:Food:Groceries"] == {"GBP": "170.00"} and "Expenses:Rent" not in rows(drill.expenses)
    assert drill.income == []


def test_a_comparison_shows_the_equal_period_before():
    report = run("2026-02-01", "2026-02-28", compare=True)
    assert (report.previous_start, report.previous_end) == (D("2026-01-04"), D("2026-01-31"))
    assert rows(report.expenses)["Expenses:Food"] == {"GBP": "150.00"}
    food = next(r for r in report.expenses if r.account == "Expenses:Food")
    assert food.previous == {"GBP": "80.00"}
    rent = next(r for r in report.expenses if r.account == "Expenses:Rent") if any(r.account == "Expenses:Rent" for r in report.expenses) else None
    assert rent is None


def test_months_and_weeks_break_the_totals_down():
    report = run("2026-01-01", "2026-02-28", interval="month")
    assert [(p.start.isoformat(), p.end.isoformat(), p.net) for p in report.periods] == [
        ("2026-01-01", "2026-01-31", {"GBP": "1920.00"}), ("2026-02-01", "2026-02-28", {"GBP": "2850.00"}),
    ]
    weeks = run("2026-02-02", "2026-02-15", interval="week")
    assert [(p.start.isoformat(), p.end.isoformat()) for p in weeks.periods] == [("2026-02-02", "2026-02-08"), ("2026-02-09", "2026-02-15")]


def test_a_period_with_nothing_is_empty_and_has_no_savings_rate():
    report = run("2026-03-01", "2026-03-31")
    assert report.income == [] and report.expenses == [] and report.net == {} and report.savings_rate is None


def test_savings_rate_is_left_out_when_currencies_are_mixed():
    mixed = loader.load_string(LEDGER + """
2026-02-08 * "Trip"
  Expenses:Rent   20.00 EUR
  Assets:Bank    -20.00 EUR
""")[0]
    report = income_statement(mixed, "main", D("2026-02-01"), D("2026-02-28"), 2, None, None, False)
    assert report.savings_rate is None and report.expense_total == {"EUR": "20.00", "GBP": "150.00"}
