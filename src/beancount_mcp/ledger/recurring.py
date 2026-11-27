"""Schedules: which dates a recurring item falls on, which are already recorded, and patterns worth proposing.

Pure functions over transactions, so the same logic serves the view, the agent tools and the web interface.
"""

import calendar
import datetime as dt
import re
from collections import defaultdict
from decimal import Decimal

from beancount_mcp.models import Transaction
from beancount_mcp.models.common import Amount
from beancount_mcp.models.recurring import Occurrence, Recurring, RecurringStatus, RecurringSuggestion

DEFAULT_WITHIN_DAYS = 14
DEFAULT_LOOKBACK_DAYS = 45
EARLY_DAYS = 3
LATE_DAYS = 14
MAX_STEPS = 5000


def add_months(day: dt.date, months: int, anchor_day: int | None = None) -> dt.date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return dt.date(year, month, min(anchor_day or day.day, calendar.monthrange(year, month)[1]))


def dates(item: Recurring, since: dt.date, until: dt.date) -> list[dt.date]:
    """Every due date in [since, until]. Months keep the day of `start`, clamped in short months."""
    found = []
    for n in range(MAX_STEPS):
        if item.every == "week":
            current = item.start + dt.timedelta(weeks=item.interval * n)
        else:
            current = add_months(item.start, item.interval * n * (12 if item.every == "year" else 1), item.start.day)
        if current > until or (item.end is not None and current > item.end):
            break
        if current >= since:
            found.append(current)
    return found


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def schedule_text(item: Recurring) -> str:
    unit = item.every if item.interval == 1 else f"{item.interval} {item.every}s"
    prefix = f"every {unit}"
    if item.every == "week":
        return f"{prefix} on {item.start:%A}"
    if item.every == "month":
        return f"{prefix} on the {_ordinal(item.start.day)}"
    return f"{prefix} on {item.start.day} {item.start:%B}"


def _moved(transaction: Transaction, account: str, currency: str) -> Decimal:
    return sum((p.units.number for p in transaction.postings if p.account == account and p.units and p.units.currency == currency), Decimal(0))


def _candidates(rid: str, item: Recurring, transactions: list[Transaction]) -> list[Transaction]:
    return [
        t for t in transactions
        if {item.from_account, item.to_account} <= {p.account for p in t.postings}
        and (t.meta.get("recurring") == rid or item.variable or abs(_moved(t, item.to_account, item.amount.currency)) == item.amount.number)
    ]


def status(rid: str, item: Recurring, transactions: list[Transaction], today: dt.date, within_days: int, lookback_days: int) -> RecurringStatus:
    candidates = _candidates(rid, item, transactions)
    claimed: set[str] = set()
    open_dates = []
    for due in dates(item, today - dt.timedelta(days=lookback_days), today + dt.timedelta(days=within_days)):
        exact = next((t for t in candidates if t.id not in claimed and t.meta.get("recurring") == rid and t.meta.get("due") == due.isoformat()), None)
        loose = next((
            t for t in sorted(candidates, key=lambda t: t.date)
            if t.id not in claimed and "recurring" not in t.meta and due - dt.timedelta(days=EARLY_DAYS) <= t.date <= due + dt.timedelta(days=LATE_DAYS)
        ), None)
        match = exact or loose
        if match is not None:
            claimed.add(match.id)
        else:
            open_dates.append(due)
    upcoming = dates(item, today, today + dt.timedelta(days=400))
    return RecurringStatus(
        id=rid, title=item.title, schedule=schedule_text(item), from_account=item.from_account, to_account=item.to_account,
        amount=item.amount, variable=item.variable, payee=item.payee, narration=item.narration, next_due=upcoming[0] if upcoming else None,
        last_paid=max((t.date for t in candidates), default=None),
        occurrences=[Occurrence(date=d, status="overdue" if d < today else "due" if d == today else "upcoming") for d in open_dates],
    )


# A spacing is recognised when every gap in the run falls in its band: (low, high, unit, interval, occurrences needed).
_BANDS = [(5, 9, "week", 1, 3), (12, 16, "week", 2, 3), (26, 33, "month", 1, 3), (86, 95, "month", 3, 3), (360, 372, "year", 1, 2)]


def slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "item"
    return slug if slug[0].isalpha() else f"r-{slug}"


def suggest(transactions: list[Transaction], existing: dict[str, Recurring], today: dt.date) -> list[RecurringSuggestion]:
    """Payments that repeat at a steady spacing and are not yet covered, from two-posting transactions in one currency."""
    groups: dict[tuple, list[tuple[dt.date, Decimal]]] = defaultdict(list)
    for t in transactions:
        if len(t.postings) != 2 or t.date > today or (today - t.date).days > 800 or any(p.units is None for p in t.postings):
            continue
        paid, received = sorted(t.postings, key=lambda p: p.units.number)
        label = (t.payee or t.narration or "").strip()
        if label and paid.units.currency == received.units.currency and received.units.number > 0:
            groups[(label.lower(), paid.account, received.account, paid.units.currency)].append((t.date, received.units.number))
    covered = {(r.from_account, r.to_account) for r in existing.values()}
    found = []
    for (key_label, source, target, currency), rows in groups.items():
        rows.sort()
        if (source, target) in covered or len(rows) < 2:
            continue
        last_gap = (rows[-1][0] - rows[-2][0]).days
        band = next((b for b in _BANDS if b[0] <= last_gap <= b[1]), None)
        if band is None:
            continue
        run = [rows[-1]]
        for earlier in reversed(rows[:-1]):
            if not band[0] <= (run[0][0] - earlier[0]).days <= band[1]:
                break
            run.insert(0, earlier)
        _, _, unit, interval, needed = band
        if len(run) < needed or (today - run[-1][0]).days > 2 * band[1]:
            continue
        amounts = [amount for _, amount in run]
        label = next(t.payee or t.narration for t in transactions if (t.payee or t.narration or "").strip().lower() == key_label and t.date == run[-1][0])
        last = run[-1][0]
        start = last + dt.timedelta(weeks=interval) if unit == "week" else add_months(last, interval * (12 if unit == "year" else 1), last.day)
        title = label.strip()
        found.append(RecurringSuggestion(
            id=slug(title), seen=len(run), last_seen=last,
            recurring=Recurring(
                title=title, from_account=source, to_account=target, amount=Amount(number=amounts[-1], currency=currency),
                every=unit, interval=interval, start=start, payee=title, variable=max(amounts) > min(amounts) * Decimal("1.05"),
            ),
        ))
    return sorted(found, key=lambda s: s.id)
