import datetime as dt
from decimal import Decimal

from beancount_mcp.models.views import ReferenceRateStatus
from beancount_mcp.services.reference_rates import RateResult
from beancount_mcp.services.views import _carried_forward, _inherited


def quiet() -> ReferenceRateStatus:
    return ReferenceRateStatus(enabled=True, state="fresh")


def test_a_day_the_provider_skipped_keeps_the_last_known_rates():
    rows = {
        dt.date(2026, 3, 1): RateResult({"CNY": Decimal("0.125")}, quiet()),
        dt.date(2026, 3, 2): RateResult({}, quiet()),
    }

    filled, inherited = _carried_forward(rows, {"CNY"})

    assert filled[dt.date(2026, 3, 2)].rates == {"CNY": Decimal("0.125")}
    assert inherited == {dt.date(2026, 3, 2): dt.date(2026, 3, 1)}
    assert filled[dt.date(2026, 3, 1)].rates == {"CNY": Decimal("0.125")}


def test_a_day_with_a_partial_answer_is_completed_and_marked():
    rows = {
        dt.date(2026, 3, 1): RateResult({"CNY": Decimal("0.125"), "USD": Decimal("1")}, quiet()),
        dt.date(2026, 3, 2): RateResult({"USD": Decimal("2")}, quiet()),
    }

    filled, inherited = _carried_forward(rows, {"CNY", "USD"})

    assert filled[dt.date(2026, 3, 2)].rates == {"CNY": Decimal("0.125"), "USD": Decimal("2")}
    assert inherited == {dt.date(2026, 3, 2): dt.date(2026, 3, 1)}


def test_a_day_before_any_rate_stays_empty():
    rows = {
        dt.date(2026, 3, 1): RateResult({}, quiet()),
        dt.date(2026, 3, 2): RateResult({"CNY": Decimal("0.125")}, quiet()),
    }

    filled, inherited = _carried_forward(rows, {"CNY"})

    assert filled[dt.date(2026, 3, 1)].rates == {}
    assert inherited == {}


def test_an_inherited_point_says_where_its_rate_came_from():
    status = _inherited(quiet(), ["CNY"], dt.date(2026, 2, 28))

    assert status.state == "stale"
    assert status.message == "carried forward from 2026-02-28"
    assert status.covered_currencies == ["CNY"]
    assert status.missing_currencies == []
