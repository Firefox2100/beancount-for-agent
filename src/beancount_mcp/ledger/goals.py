"""How far savings goals have got. Straight arithmetic on balances: no forecasting method is involved."""

import datetime as dt
from decimal import ROUND_CEILING, Decimal

from beancount_mcp.ledger.conversion import Rates, counted, money
from beancount_mcp.ledger.recurring import add_months
from beancount_mcp.models.goals import Goal, GoalStatus


def holdings(balances: dict[str, dict[str, Decimal]], goal: Goal) -> dict[str, Decimal]:
    """What the goal's accounts and their sub-accounts hold, per currency."""
    held: dict[str, Decimal] = {}
    for account, amounts in balances.items():
        if any(account == name or account.startswith(name + ":") for name in goal.accounts):
            for currency, number in amounts.items():
                held[currency] = held.get(currency, Decimal(0)) + number
    return held


def months_between(today: dt.date, by: dt.date) -> int:
    """Whole months from today to `by`, never negative."""
    months = (by.year - today.year) * 12 + by.month - today.month
    return max(months - (1 if by.day < today.day else 0), 0)


def status(goal_id: str, goal: Goal, balances: dict[str, dict[str, Decimal]], today: dt.date, rates: Rates | None = None) -> GoalStatus:
    currency, target = goal.target.currency, goal.target.number
    saved, converted, unconverted = counted(holdings(balances, goal), currency, rates or {})
    remaining = max(target - saved, Decimal(0))
    reached = remaining == 0
    months = months_between(today, goal.by) if goal.by else None
    needed = None
    if goal.by is not None and not reached:
        needed = money(remaining / max(months or 0, 1))
    planned = goal.monthly if goal.monthly and goal.monthly.currency == currency and goal.monthly.number > 0 else None
    projected = None
    if planned is not None and not reached:
        projected = add_months(today, int((remaining / planned.number).to_integral_value(ROUND_CEILING)))
    if reached:
        state = "reached"
    elif goal.by is None:
        state = "open"
    elif projected is not None:
        state = "on_track" if projected <= goal.by else "behind"
    else:
        state = "behind" if goal.by <= today else "open"
    return GoalStatus(
        id=goal_id, title=goal.title, accounts=goal.accounts, target=goal.target, saved=money(saved), approximate=bool(converted),
        converted=converted, other_currencies={c: money(n) for c, n in sorted(unconverted.items())}, remaining=money(remaining),
        percent=money(min(saved / target * 100, Decimal(100))) if target > 0 else "100.00", reached=reached, by=goal.by,
        months_left=months, needed_monthly=needed, planned_monthly=goal.monthly, projected=projected, state=state,
    )
