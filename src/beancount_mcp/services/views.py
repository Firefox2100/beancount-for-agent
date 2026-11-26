import asyncio
import datetime as dt

from beancount_mcp.ledger import views
from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.ledger.profile import ProfileStore
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models.views import DueItem, OpenItems, PoolStatus


class ViewService:
    """Summaries that answer "what is open, due or available" without the caller adding up postings."""

    def __init__(self, store: LedgerStore):
        self._store = store

    async def open_items(self, ledger_id: str, account: str | None) -> list[OpenItems]:
        return await asyncio.to_thread(self._open_items, ledger_id, account)

    async def due(self, ledger_id: str, within_days: int | None, today: dt.date | None) -> list[DueItem]:
        return await asyncio.to_thread(self._due, ledger_id, within_days, today or dt.date.today())

    async def pools(self, ledger_id: str, today: dt.date | None) -> list[PoolStatus]:
        return await asyncio.to_thread(self._pools, ledger_id, today or dt.date.today())

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
