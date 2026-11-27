"""Budget periods and how spending is going against them. Pure functions over the loaded entries."""

import calendar
import datetime as dt
from collections import defaultdict
from decimal import ROUND_CEILING, Decimal

from beancount_mcp.ledger.recurring import add_months, slug
from beancount_mcp.ledger.reports import collect, total_of
from beancount_mcp.ledger.conversion import Rates, counted, money
from beancount_mcp.models.budgets import Budget, BudgetStatus, BudgetSuggestion, PeriodSpent
from beancount_mcp.models.common import Amount

HISTORY = 3
SUGGEST_MONTHS = 3
AHEAD_MARGIN = Decimal("0.10")


def period_of(budget: Budget, day: dt.date) -> tuple[dt.date, dt.date]:
    """The period of `budget` that contains `day`, as first and last day."""
    if budget.every == "week":
        start = day - dt.timedelta(days=day.weekday())
        return start, start + dt.timedelta(days=6)
    if budget.every == "year":
        return dt.date(day.year, 1, 1), dt.date(day.year, 12, 31)
    start = day.replace(day=budget.start_day) if day.day >= budget.start_day else add_months(day, -1, budget.start_day)
    return start, add_months(start, 1, budget.start_day) - dt.timedelta(days=1)


def spent(entries: list, prefix: str, start: dt.date, end: dt.date) -> dict[str, Decimal]:
    return dict(total_of(collect(entries, start, end, prefix, 99)[1]))


def status(budget_id: str, budget: Budget, entries: list, today: dt.date, rates: Rates | None = None) -> BudgetStatus:
    rates = rates or {}
    start, end = period_of(budget, today)
    currency, limit = budget.amount.currency, budget.amount.number
    used, converted, unconverted = counted(spent(entries, budget.account, start, end), currency, rates)
    total_days, elapsed = (end - start).days + 1, (today - start).days + 1
    fraction = Decimal(elapsed) / Decimal(total_days)
    left = (end - today).days
    remaining = limit - used
    state = "over" if used > limit else "ahead" if limit > 0 and used / limit > fraction + AHEAD_MARGIN else "ok"
    history, cursor = [], start
    for _ in range(HISTORY):
        before_start, before_end = period_of(budget, cursor - dt.timedelta(days=1))
        amount = counted(spent(entries, budget.account, before_start, before_end), currency, rates)[0]
        history.append(PeriodSpent(start=before_start, end=before_end, spent=money(amount), over=amount > limit))
        cursor = before_start
    return BudgetStatus(
        id=budget_id, title=budget.title or budget.account.rsplit(":", 1)[-1], account=budget.account, limit=budget.amount,
        every=budget.every, start=start, end=end, spent=money(used), remaining=money(remaining),
        used_percent=money(used / limit * 100) if limit > 0 else "0.00", state=state, days_left=left,
        projected=money(used / fraction), daily_allowance=money(remaining / left) if remaining > 0 and left > 0 else None,
        approximate=bool(converted), converted=converted,
        other_currencies={c: money(n) for c, n in sorted(unconverted.items())}, history=history,
    )


def _round_up(value: Decimal) -> Decimal:
    step = Decimal(5) if value < 100 else Decimal(10) if value < 500 else Decimal(50)
    return (value / step).to_integral_value(ROUND_CEILING) * step


def suggest(entries: list, existing: dict[str, Budget], today: dt.date) -> list[BudgetSuggestion]:
    """A monthly budget for each expense group (two name segments) with spending in at least two of the last whole months."""
    first_of_month = today.replace(day=1)
    months = [add_months(first_of_month, -n) for n in range(SUGGEST_MONTHS, 0, -1)]
    per_group: dict[str, dict[str, list[Decimal]]] = defaultdict(lambda: defaultdict(list))
    for month in months:
        last = month.replace(day=calendar.monthrange(month.year, month.month)[1])
        for group, amounts in collect(entries, month, last, None, 2)[1].items():
            for currency, number in amounts.items():
                per_group[group][currency].append(number)
    covered = {b.account for b in existing.values()}
    found = []
    for group, by_currency in sorted(per_group.items()):
        if group in covered or any(group.startswith(c + ":") or c.startswith(group + ":") for c in covered):
            continue
        currency, amounts = max(by_currency.items(), key=lambda item: sum(item[1]))
        if len(amounts) < 2:
            continue
        average = sum(amounts, Decimal(0)) / SUGGEST_MONTHS
        if average < 10:
            continue
        found.append(BudgetSuggestion(
            id=slug(group.split(":", 1)[1] if ":" in group else group), average=money(average), months=len(amounts),
            budget=Budget(account=group, amount=Amount(number=_round_up(average), currency=currency)),
        ))
    return found
