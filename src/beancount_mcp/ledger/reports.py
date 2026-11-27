"""Income and expenses over a period, computed from the entries. Amounts stay in the currencies they were booked in."""

import calendar
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from beancount.core import data

from beancount_mcp.models.reports import AccountTotal, IncomeStatement, PeriodTotal

Totals = dict[str, dict[str, Decimal]]


def _format(totals: dict[str, Decimal]) -> dict[str, str]:
    return {c: format(n, "f") for c, n in sorted(totals.items()) if n != 0}


def collect(entries: list, start: dt.date, end: dt.date, prefix: str | None, depth: int) -> tuple[Totals, Totals]:
    """Per grouped account: income (positive when earned) and expenses (positive when spent), within [start, end]."""
    income: Totals = defaultdict(lambda: defaultdict(Decimal))
    expenses: Totals = defaultdict(lambda: defaultdict(Decimal))
    for entry in entries:
        if not isinstance(entry, data.Transaction) or not start <= entry.date <= end:
            continue
        for posting in entry.postings:
            if posting.units is None or posting.units.number is None:
                continue
            root = posting.account.split(":", 1)[0]
            if root not in ("Income", "Expenses") or (prefix and not (posting.account == prefix or posting.account.startswith(prefix + ":"))):
                continue
            name = ":".join(posting.account.split(":")[:depth])
            if root == "Income":
                income[name][posting.units.currency] -= posting.units.number
            else:
                expenses[name][posting.units.currency] += posting.units.number
    return income, expenses


def total_of(groups: Totals) -> dict[str, Decimal]:
    total: dict[str, Decimal] = defaultdict(Decimal)
    for amounts in groups.values():
        for currency, number in amounts.items():
            total[currency] += number
    return total


def _rows(now: Totals, before: Totals | None) -> list[AccountTotal]:
    names = set(now) | (set(before) if before is not None else set())
    rows = [
        AccountTotal(
            account=name, totals=_format(now.get(name, {})),
            previous=_format(before.get(name, {})) if before is not None else None,
        )
        for name in names
    ]
    rows = [r for r in rows if r.totals or r.previous]
    return sorted(rows, key=lambda r: (-sum((Decimal(v) for v in r.totals.values()), Decimal(0)), r.account))


def _net(income: dict[str, Decimal], expenses: dict[str, Decimal]) -> dict[str, Decimal]:
    return {c: income.get(c, Decimal(0)) - expenses.get(c, Decimal(0)) for c in set(income) | set(expenses)}


def _periods(start: dt.date, end: dt.date, interval: str) -> list[tuple[dt.date, dt.date]]:
    spans, current = [], start
    while current <= end:
        if interval == "week":
            stop = min(current + dt.timedelta(days=6 - current.weekday()), end)
        else:
            stop = min(current.replace(day=calendar.monthrange(current.year, current.month)[1]), end)
        spans.append((current, stop))
        current = stop + dt.timedelta(days=1)
    return spans


def income_statement(
    entries: list, ledger: str, start: dt.date, end: dt.date, depth: int, prefix: str | None, interval: str | None, compare: bool
) -> IncomeStatement:
    income, expenses = collect(entries, start, end, prefix, depth)
    before_income = before_expenses = None
    previous_start = previous_end = None
    if compare:
        length = (end - start).days + 1
        previous_end, previous_start = start - dt.timedelta(days=1), start - dt.timedelta(days=length)
        before_income, before_expenses = collect(entries, previous_start, previous_end, prefix, depth)
    income_total, expense_total = total_of(income), total_of(expenses)
    net = _net(income_total, expense_total)
    currencies = {c for c, n in {**income_total, **expense_total}.items() if n != 0}
    earned = income_total.get(next(iter(currencies)), Decimal(0)) if len(currencies) == 1 else Decimal(0)
    rate = None
    if len(currencies) == 1 and earned > 0:
        rate = format((net[next(iter(currencies))] / earned * 100).quantize(Decimal("0.1")), "f")
    periods = []
    for span_start, span_end in _periods(start, end, interval) if interval else []:
        span_income, span_expenses = (total_of(g) for g in collect(entries, span_start, span_end, prefix, depth))
        periods.append(PeriodTotal(
            start=span_start, end=span_end, income=_format(span_income), expenses=_format(span_expenses),
            net=_format(_net(span_income, span_expenses)),
        ))
    return IncomeStatement(
        ledger=ledger, start=start, end=end, depth=depth,
        income=_rows(income, before_income), expenses=_rows(expenses, before_expenses),
        income_total=_format(income_total), expense_total=_format(expense_total), net=_format(net), savings_rate=rate,
        previous_start=previous_start, previous_end=previous_end, periods=periods, interval=interval,  # type: ignore[arg-type]
    )
