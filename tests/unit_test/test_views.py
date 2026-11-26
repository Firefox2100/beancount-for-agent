from datetime import date

from beancount_mcp.ledger.views import _next_day


def test_next_day_this_month_or_next():
    assert _next_day(20, date(2026, 3, 5)) == date(2026, 3, 20)
    assert _next_day(5, date(2026, 3, 5)) == date(2026, 3, 5)
    assert _next_day(4, date(2026, 3, 5)) == date(2026, 4, 4)


def test_next_day_clamps_short_months_and_wraps_the_year():
    assert _next_day(31, date(2026, 2, 10)) == date(2026, 2, 28)
    assert _next_day(10, date(2026, 12, 20)) == date(2027, 1, 10)
