import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from beancount_mcp.ledger.recurring import dates, schedule_text, status, suggest
from beancount_mcp.models import Posting, Transaction
from beancount_mcp.models.common import Amount
from beancount_mcp.models.recurring import Recurring

D = dt.date.fromisoformat


def item(**overrides) -> Recurring:
    values = dict(title="Rent", from_account="Assets:Bank", to_account="Expenses:Rent",
                  amount=Amount(number=Decimal("1200"), currency="GBP"), start=D("2026-01-01"))
    return Recurring(**{**values, **overrides})


def tx(day, amount="1200", to="Expenses:Rent", source="Assets:Bank", payee=None, narration="", meta=None, ident=None, currency="GBP"):
    return Transaction(
        id=ident or f"{source}{to}{day}", date=D(day), payee=payee, narration=narration, meta=meta or {},
        postings=[Posting(account=to, units=Amount(number=Decimal(amount), currency=currency)),
                  Posting(account=source, units=Amount(number=-Decimal(amount), currency=currency))],
    )


def test_monthly_dates_keep_the_day_and_clamp_in_short_months():
    found = dates(item(start=D("2026-01-31")), D("2026-01-01"), D("2026-05-01"))
    assert found == [D("2026-01-31"), D("2026-02-28"), D("2026-03-31"), D("2026-04-30")]


def test_weekly_yearly_intervals_and_an_end_date():
    assert dates(item(every="week", interval=2, start=D("2026-01-05")), D("2026-01-01"), D("2026-02-10")) == [D("2026-01-05"), D("2026-01-19"), D("2026-02-02")]
    assert dates(item(every="year", start=D("2024-02-29")), D("2025-01-01"), D("2027-12-31")) == [D("2025-02-28"), D("2026-02-28"), D("2027-02-28")]
    assert dates(item(end=D("2026-03-01")), D("2026-01-01"), D("2026-12-31")) == [D("2026-01-01"), D("2026-02-01"), D("2026-03-01")]
    assert dates(item(start=D("2026-06-01")), D("2026-01-01"), D("2026-05-01")) == []


def test_schedules_read_naturally():
    assert schedule_text(item(start=D("2026-01-01"))) == "every month on the 1st"
    assert schedule_text(item(start=D("2026-01-22"), interval=3)) == "every 3 months on the 22nd"
    assert schedule_text(item(every="week", start=D("2026-01-05"))) == "every week on Monday"
    assert schedule_text(item(every="year", start=D("2026-03-03"))) == "every year on 3 March"
    assert schedule_text(item(start=D("2026-01-12"))).endswith("12th") and schedule_text(item(start=D("2026-01-23"))).endswith("23rd")


def test_an_item_needs_two_different_accounts_and_a_positive_interval():
    with pytest.raises(ValidationError):
        item(to_account="Assets:Bank")
    with pytest.raises(ValidationError):
        item(interval=0)


def test_unrecorded_occurrences_are_overdue_due_or_upcoming():
    result = status("rent", item(), [tx("2026-01-02")], D("2026-03-01"), 14, 90)
    assert [(o.date.isoformat(), o.status) for o in result.occurrences] == [("2026-02-01", "overdue"), ("2026-03-01", "due")]
    assert result.last_paid == D("2026-01-02") and result.next_due == D("2026-03-01")
    later = status("rent", item(), [], D("2026-03-20"), 14, 30)
    assert [o.status for o in later.occurrences] == ["overdue", "upcoming"]


def test_a_payment_a_few_days_off_still_counts_and_is_counted_once():
    ledger = [tx("2025-12-30"), tx("2026-02-06")]
    result = status("rent", item(), ledger, D("2026-02-10"), 0, 60)
    assert result.occurrences == []
    one = status("rent", item(), [tx("2026-02-01")], D("2026-03-10"), 0, 60)
    assert [o.date for o in one.occurrences] == [D("2026-03-01")]


def test_a_payment_of_another_amount_is_not_the_item_unless_the_amount_varies():
    assert status("rent", item(), [tx("2026-02-01", "900")], D("2026-02-05"), 0, 10).occurrences
    assert not status("rent", item(variable=True), [tx("2026-02-01", "900")], D("2026-02-05"), 0, 10).occurrences


def test_a_tagged_transaction_settles_exactly_the_occurrence_it_names():
    paid_late = tx("2026-02-20", meta={"recurring": "rent", "due": "2026-01-01"})
    result = status("rent", item(), [paid_late], D("2026-02-21"), 0, 60)
    assert [o.date for o in result.occurrences] == [D("2026-02-01")]


def test_suggestions_find_steady_payments_and_skip_covered_or_lapsed_ones():
    ledger = [
        *[tx(f"2026-0{m}-05", "9.99", to="Expenses:Music", payee="Spotify", ident=f"s{m}") for m in (1, 2, 3, 4)],
        *[tx(f"2026-0{m}-{d}", "30", to="Expenses:Food", payee="Cafe", ident=f"c{m}") for m, d in ((1, "03"), (2, "19"), (4, "02"))],
        *[tx(f"2025-0{m}-05", "5", to="Expenses:Old", payee="Gym", ident=f"g{m}") for m in (1, 2, 3)],
        *[tx(f"2026-0{m}-01", "1200", ident=f"r{m}") for m in (1, 2, 3, 4)],
    ]
    found = suggest(ledger, {}, D("2026-04-20"))
    assert [s.id for s in found] == ["rent", "spotify"] or [s.id for s in found] == ["spotify"]
    spotify = next(s for s in found if s.id == "spotify")
    assert (spotify.recurring.every, spotify.recurring.interval, spotify.seen, spotify.recurring.start) == ("month", 1, 4, D("2026-05-05"))
    assert spotify.recurring.amount.number == Decimal("9.99") and not spotify.recurring.variable
    covered = suggest(ledger, {"music": item(to_account="Expenses:Music")}, D("2026-04-20"))
    assert "spotify" not in [s.id for s in covered]


def test_varying_amounts_are_marked_variable():
    ledger = [tx(f"2026-0{m}-10", amount, to="Expenses:Power", payee="Power Co", ident=f"p{m}") for m, amount in ((1, "80"), (2, "95"), (3, "70"))]
    (found,) = suggest(ledger, {}, D("2026-03-20"))
    assert found.recurring.variable and found.recurring.amount.number == Decimal("70")
