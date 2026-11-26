"""Read-only summaries computed from the loaded entries and the profile."""

import calendar
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from beancount.core import data, prices

from beancount_mcp.models import AccountInfo, Profile
from beancount_mcp.models.views import DueItem, OpenItem, OpenItems, PoolMember, PoolStatus

OPEN_ITEM_KINDS = {"receivable", "payable"}


def _format(totals: dict[str, Decimal]) -> dict[str, str]:
    return {c: format(n, "f") for c, n in sorted(totals.items()) if n != 0}


def _postings(entries: list, account: str):
    for entry in entries:
        if isinstance(entry, data.Transaction):
            units = [p.units for p in entry.postings if p.account == account and p.units and p.units.number is not None]
            if units:
                yield entry, units


def open_items(entries: list, account: str) -> OpenItems:
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    firsts: dict[str, data.Transaction] = {}
    counts: dict[str, int] = defaultdict(int)
    unlinked: dict[str, Decimal] = defaultdict(Decimal)
    balance: dict[str, Decimal] = defaultdict(Decimal)

    for entry, units in _postings(entries, account):
        for amount in units:
            balance[amount.currency] += amount.number
            if not entry.links:
                unlinked[amount.currency] += amount.number
            for link in entry.links:
                totals[link][amount.currency] += amount.number
        for link in entry.links:
            counts[link] += 1
            if link not in firsts:
                firsts[link] = entry

    items = [
        OpenItem(
            link=link,
            account=account,
            opened=firsts[link].date,
            payee=firsts[link].payee,
            narration=firsts[link].narration or "",
            balances=_format(amounts),
            transactions=counts[link],
        )
        for link, amounts in totals.items()
        if any(number != 0 for number in amounts.values())
    ]
    items.sort(key=lambda item: (item.opened, item.link))
    return OpenItems(account=account, items=items, unlinked=_format(unlinked), balance=_format(balance))


def open_item_accounts(accounts: list[AccountInfo]) -> list[str]:
    return [a.name for a in accounts if a.type in OPEN_ITEM_KINDS and a.close_date is None]


def _next_day(day: int, today: dt.date) -> dt.date:
    """The first date on or after `today` that falls on `day` of a month, clamped to short months."""
    year, month = today.year, today.month
    for _ in range(2):
        candidate = dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if candidate >= today:
            return candidate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def due_items(
    entries: list, accounts: list[AccountInfo], profile: Profile, today: dt.date, within_days: int | None
) -> list[DueItem]:
    balances = _balances(entries)
    result = []
    for info in accounts:
        settings = profile.accounts.get(info.name)
        if info.close_date is not None or settings is None or not info.name.startswith("Liabilities:"):
            continue
        if settings.due_day is None and settings.statement_day is None:
            continue
        unbilled_name = settings.unbilled_account or f"{info.name}:Unbilled"
        owed = {c: -n for c, n in balances.get(info.name, {}).items() if n < 0}
        unbilled = {c: -n for c, n in balances.get(unbilled_name, {}).items() if n < 0}
        due = _next_day(settings.due_day, today) if settings.due_day else None
        days = (due - today).days if due else None
        if within_days is not None and (not owed or days is None or days > within_days):
            continue
        result.append(
            DueItem(
                account=info.name,
                description=settings.description,
                owed=_format(owed),
                unbilled=_format(unbilled),
                next_statement=_next_day(settings.statement_day, today) if settings.statement_day else None,
                due_date=due,
                days_until_due=days,
                autopay_from=settings.autopay_from,
            )
        )
    result.sort(key=lambda item: (item.due_date or dt.date.max, item.account))
    return result


def _balances(entries: list) -> dict[str, dict[str, Decimal]]:
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for entry in entries:
        if isinstance(entry, data.Transaction):
            for posting in entry.postings:
                if posting.units is not None and posting.units.number is not None:
                    totals[posting.account][posting.units.currency] += posting.units.number
    return totals


def pool_status(entries: list, profile: Profile, today: dt.date) -> list[PoolStatus]:
    balances = _balances(entries)
    price_map = prices.build_price_map(entries)
    result = []
    for name, pool in sorted(profile.pools.items()):
        target = pool.limit.currency
        used = Decimal(0)
        unconverted: dict[str, Decimal] = defaultdict(Decimal)
        members = []
        for account, settings in sorted(profile.accounts.items()):
            if settings.pool != name:
                continue
            owed: dict[str, Decimal] = defaultdict(Decimal)
            for held, amounts in balances.items():
                if held == account or held.startswith(account + ":"):
                    for currency, number in amounts.items():
                        owed[currency] += -number
            members.append(PoolMember(account=account, owed=_format(owed)))
            for currency, number in owed.items():
                if number == 0:
                    continue
                if currency == target:
                    used += number
                    continue
                _, rate = prices.get_price(price_map, (currency, target), today)
                if rate is None:
                    unconverted[currency] += number
                else:
                    used += number * rate
        used = used.quantize(Decimal("0.01"))
        result.append(
            PoolStatus(
                name=name,
                limit=pool.limit,
                used=format(used, "f"),
                available=format(pool.limit.number - used, "f"),
                members=members,
                unconverted=_format(unconverted),
            )
        )
    return result
