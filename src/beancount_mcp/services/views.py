import asyncio
import calendar
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from beancount_mcp.ledger import views
from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.ledger.profile import ProfileStore
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models.views import (
    AllocationItem, DueItem, FinancialPosition, OpenItems, PoolStatus, PositionPoint,
    PositionTotal, ReferenceRateStatus, ReferenceValue,
)
from beancount_mcp.services.reference_rates import ReferenceRateService


class ViewService:
    """Summaries that answer "what is open, due or available" without the caller adding up postings."""

    def __init__(self, store: LedgerStore, reference_rates: ReferenceRateService):
        self._store = store
        self._rates = reference_rates

    async def open_items(self, ledger_id: str, account: str | None) -> list[OpenItems]:
        return await asyncio.to_thread(self._open_items, ledger_id, account)

    async def due(self, ledger_id: str, within_days: int | None, today: dt.date | None) -> list[DueItem]:
        return await asyncio.to_thread(self._due, ledger_id, within_days, today or dt.date.today())

    async def pools(self, ledger_id: str, today: dt.date | None) -> list[PoolStatus]:
        return await asyncio.to_thread(self._pools, ledger_id, today or dt.date.today())

    async def financial_position(
        self, ledger_id: str, interval: str, points: int, today: dt.date | None = None
    ) -> FinancialPosition:
        return await asyncio.to_thread(self._financial_position, ledger_id, interval, points, today or dt.date.today())

    async def reference_rate_status(self) -> ReferenceRateStatus:
        return await asyncio.to_thread(self._rates.status)

    async def refresh_reference_rates(self) -> ReferenceRateStatus:
        return await asyncio.to_thread(self._rates.refresh)

    def _open_items(self, ledger_id: str, account: str | None) -> list[OpenItems]:
        ledger = self._store.open(ledger_id)
        entries = ledger.load()[0]
        accounts = ledger.accounts()
        if account is not None:
            if account not in {a.name for a in accounts}:
                raise RecipeError(f"account {account} does not exist")
            names = [account]
        else:
            names = views.open_item_accounts(accounts)
        return [views.open_items(entries, name) for name in names]

    def _due(self, ledger_id: str, within_days: int | None, today: dt.date) -> list[DueItem]:
        ledger = self._store.open(ledger_id)
        profile = ProfileStore(ledger.root).load()[0]
        return views.due_items(ledger.load()[0], ledger.accounts(), profile, today, within_days)

    def _pools(self, ledger_id: str, today: dt.date) -> list[PoolStatus]:
        ledger = self._store.open(ledger_id)
        profile = ProfileStore(ledger.root).load()[0]
        return views.pool_status(ledger.load()[0], profile, today)

    def _financial_position(self, ledger_id: str, interval: str, count: int, today: dt.date) -> FinancialPosition:
        ledger = self._store.open(ledger_id)
        currencies = ledger.operating_currencies()
        if not currencies:
            raise RecipeError("the ledger needs an operating currency for reference valuations")
        base = currencies[0]
        dates = _point_dates(today, interval, count)
        holdings: list[tuple[dt.date, dict[str, Decimal], dict[str, Decimal]]] = []
        quotes: set[str] = set()
        for date in dates:
            held_assets, held_liabilities = _position_totals(ledger.balances(date))
            holdings.append((date, held_assets, held_liabilities))
            quotes |= held_assets.keys() | held_liabilities.keys()
        rate_rows = self._rates.rates_for(base, quotes, dates)
        position_points: list[PositionPoint] = []
        for date, held_assets, held_liabilities in holdings:
            priced = rate_rows[date]
            position_points.append(PositionPoint(
                date=date,
                assets=_position_total(held_assets, base, priced.rates),
                liabilities=_position_total(held_liabilities, base, priced.rates),
                net=_position_total(_subtract(held_assets, held_liabilities), base, priced.rates),
                valuation=priced.status,
            ))

        current = ledger.balances(today)
        groups: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        for row in current:
            if not row.account.startswith("Assets:"):
                continue
            parts = row.account.split(":")
            group = ":".join(parts[:2])
            for currency, number in row.balances.items():
                groups[group][currency] += Decimal(number)
        today_rates = rate_rows.get(today) or self._rates.rates(base, quotes, today)
        valued = {name: _converted(amounts, base, today_rates.rates) for name, amounts in groups.items()}
        denominator = sum((value for value in valued.values() if value is not None and value > 0), Decimal(0))
        allocation = [
            AllocationItem(
                account=name,
                original=_formatted(amounts),
                reference_value=_reference(valued[name], base),
                share=None if valued[name] is None or denominator == 0 else format((valued[name] / denominator * 100).quantize(Decimal("0.01")), "f"),
            )
            for name, amounts in sorted(groups.items())
        ]
        status = today_rates.status if quotes else self._rates.status()
        return FinancialPosition(
            ledger=ledger_id, ledger_version=ledger.version(), interval=interval, base_currency=base,
            points=position_points, allocation=allocation, valuation=status,
        )


def _point_dates(today: dt.date, interval: str, count: int) -> list[dt.date]:
    if interval == "week":
        return [today - dt.timedelta(days=7 * offset) for offset in reversed(range(count))]
    dates = []
    year, month = today.year, today.month
    for offset in reversed(range(count)):
        absolute = year * 12 + month - 1 - offset
        point_year, point_month = divmod(absolute, 12)
        if offset == 0:
            dates.append(today)
        else:
            dates.append(dt.date(point_year, point_month + 1, calendar.monthrange(point_year, point_month + 1)[1]))
    return dates


def _position_totals(rows) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    assets: dict[str, Decimal] = defaultdict(Decimal)
    liabilities: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        target = assets if row.account == "Assets" or row.account.startswith("Assets:") else liabilities if row.account == "Liabilities" or row.account.startswith("Liabilities:") else None
        if target is None:
            continue
        for currency, text in row.balances.items():
            number = Decimal(text)
            target[currency] += number if target is assets else -number
    return dict(assets), dict(liabilities)


def _subtract(left: dict[str, Decimal], right: dict[str, Decimal]) -> dict[str, Decimal]:
    return {currency: left.get(currency, Decimal(0)) - right.get(currency, Decimal(0)) for currency in left.keys() | right.keys()}


def _formatted(values: dict[str, Decimal]) -> dict[str, str]:
    return {currency: format(number, "f") for currency, number in sorted(values.items()) if number != 0}


def _converted(values: dict[str, Decimal], base: str, rates: dict[str, Decimal]) -> Decimal | None:
    total = Decimal(0)
    for currency, number in values.items():
        if currency == base:
            total += number
        elif currency in rates:
            total += number * rates[currency]
        else:
            return None
    return total.quantize(Decimal("0.01"))


def _reference(number: Decimal | None, base: str) -> ReferenceValue | None:
    return None if number is None else ReferenceValue(number=format(number, "f"), currency=base)


def _position_total(values: dict[str, Decimal], base: str, rates: dict[str, Decimal]) -> PositionTotal:
    return PositionTotal(original=_formatted(values), reference_value=_reference(_converted(values, base, rates), base))
