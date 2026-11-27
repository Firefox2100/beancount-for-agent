"""The operations agents use, shaped around intent rather than around the API.

Everything an agent writes is proposed as a pending change. The MCP tools are thin
wrappers over this class.
"""

import asyncio
import datetime as dt
from typing import Any

from pydantic_core import to_jsonable_python

from beancount_mcp.models.details import for_agent
from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models import (
    AccountBalance,
    AccountInfo,
    ActionRequest,
    AddTransaction,
    Caller,
    ChangeStatus,
    CloseAccount,
    CreateLedgerRequest,
    DeleteTransaction,
    KindInfo,
    LedgerInfo,
    OpenAccount,
    Operation,
    PendingChange,
    Posting,
    Reconcile,
    RecipeInfo,
    SubmitChangeRequest,
    Transaction,
    TransactionInput,
    UpdateTransaction,
)
from beancount_mcp.models.common import Amount
from beancount_mcp.models.views import DueItem, FinancialPosition, OpenItems, PoolStatus, ReferenceRateStatus
from beancount_mcp.recipes.helpers import Money, amount_of
from beancount_mcp.services.actions import ActionService
from beancount_mcp.services.changes import ChangeService
from beancount_mcp.services.ledgers import LedgerService
from beancount_mcp.services.resolve import resolve_account, resolve_params
from beancount_mcp.services.views import ViewService

CASH_KINDS = {"checking", "savings", "cash", "ewallet"}
FUNDING_ROOTS = ("Assets", "Liabilities")


class AgentService:
    def __init__(
        self,
        store: LedgerStore,
        ledgers: LedgerService,
        changes: ChangeService,
        actions: ActionService,
        views: ViewService,
    ):
        self._store = store
        self._ledgers = ledgers
        self._changes = changes
        self._actions = actions
        self._views = views

    async def resolve_ledger(self, ledger: str | None) -> str:
        """The named ledger, or the only one when there is exactly one."""
        if ledger:
            return ledger
        ids = [info.id for info in await self._ledgers.list_ledgers()]
        if len(ids) == 1:
            return ids[0]
        raise RecipeError(
            "no ledgers exist yet, create one first" if not ids else f"name the ledger: {', '.join(ids)}"
        )

    async def list_ledgers(self) -> list[LedgerInfo]:
        return await self._ledgers.list_ledgers()

    async def accounts(self, ledger: str | None, include_closed: bool = False) -> list[AccountInfo]:
        ledger_id = await self.resolve_ledger(ledger)
        accounts = await self._ledgers.list_accounts(ledger_id)
        visible = [a for a in accounts if include_closed or a.close_date is None]
        return [a.model_copy(update={"details": for_agent(a.details)}) for a in visible]

    async def create_ledger(self, request: CreateLedgerRequest) -> LedgerInfo:
        status = await self._ledgers.create_ledger(request)
        return LedgerInfo(id=status.id, layout=status.layout, version=status.version)

    def account_types(self) -> list[KindInfo]:
        return self._actions.list_kinds()

    async def balances(self, ledger: str | None, account: str | None, as_of: dt.date | None) -> list[AccountBalance]:
        """Balances per account. `account` keeps that account and its sub-accounts."""
        ledger_id = await self.resolve_ledger(ledger)
        result = await self._ledgers.balances(ledger_id, as_of)
        prefix = await self.lookup(ledger_id, account, subtree=True)
        if prefix:
            result = [b for b in result if b.account == prefix or b.account.startswith(prefix + ":")]
        return result

    async def search(
        self, ledger: str | None, text: str | None, account: str | None, start: dt.date | None,
        end: dt.date | None, tag: str | None, limit: int,
    ) -> list[Transaction]:
        ledger_id = await self.resolve_ledger(ledger)
        account = await self.lookup(ledger_id, account, subtree=True)
        page = await self._ledgers.list_transactions(
            ledger_id, account=account, start=start, end=end, text=text, tag=tag, limit=min(limit, 100)
        )
        return page.items

    async def recipes(self, ledger: str | None, account: str) -> list[RecipeInfo]:
        ledger_id = await self.resolve_ledger(ledger)
        return await self._actions.list_recipes(ledger_id, await self.lookup(ledger_id, account))

    async def open_items(self, ledger: str | None, account: str | None) -> list[OpenItems]:
        ledger_id = await self.resolve_ledger(ledger)
        return await self._views.open_items(ledger_id, await self.lookup(ledger_id, account))

    async def due(self, ledger: str | None, within_days: int | None) -> list[DueItem]:
        return await self._views.due(await self.resolve_ledger(ledger), within_days, None)

    async def pools(self, ledger: str | None) -> list[PoolStatus]:
        return await self._views.pools(await self.resolve_ledger(ledger), None)

    async def financial_position(self, ledger: str | None, interval: str, points: int) -> FinancialPosition:
        return await self._views.financial_position(await self.resolve_ledger(ledger), interval, points)

    async def reference_rate_status(self) -> ReferenceRateStatus:
        return await self._views.reference_rate_status()

    async def submit(
        self,
        ledger: str | None,
        request: SubmitChangeRequest,
        caller: Caller,
        version: str | None,
    ) -> PendingChange:
        ledger_id = await self.resolve_ledger(ledger)
        if version is None:
            version = (await self._ledgers.get_ledger(ledger_id)).version
        return await self._changes.submit(ledger_id, request, caller, version)

    async def _find(self, ledger_id: str, name: str, roots: tuple[str, ...] | None = None) -> str:
        return resolve_account(await self._ledgers.list_accounts(ledger_id), name, roots)

    async def propose_action(
        self, ledger: str | None, account: str, recipe: str, params: dict[str, Any], note: str | None,
        caller: Caller, version: str | None,
    ) -> PendingChange:
        ledger_id = await self.resolve_ledger(ledger)
        accounts = await self._ledgers.list_accounts(ledger_id)
        account = resolve_account(accounts, account)
        params = resolve_params(accounts, params)
        request = SubmitChangeRequest(action=ActionRequest(account=account, recipe=recipe, params=params), note=note)
        return await self.submit(ledger_id, request, caller, version)

    async def propose_operation(
        self, ledger: str | None, operation: Operation, note: str | None, caller: Caller, version: str | None
    ) -> PendingChange:
        return await self.submit(ledger, SubmitChangeRequest(operation=operation, note=note), caller, version)

    async def lookup(self, ledger: str | None, name: str | None, subtree: bool = False) -> str | None:
        """An account named loosely, for read filters. With `subtree`, a bare prefix such as Assets also passes."""
        if not name:
            return None
        ledger_id = await self.resolve_ledger(ledger)
        accounts = await self._ledgers.list_accounts(ledger_id)
        try:
            return resolve_account(accounts, name)
        except RecipeError:
            if subtree and any(a.name.startswith(name + ":") for a in accounts):
                return name
            raise

    async def _kind(self, ledger_id: str, account: str) -> tuple[str | None, AccountInfo]:
        info = next((a for a in await self._ledgers.list_accounts(ledger_id) if a.name == account), None)
        if info is None or info.close_date is not None:
            raise RecipeError(f"account {account} is not open")
        return info.type, info

    async def expense(
        self, ledger: str | None, from_account: str, expense_account: str, amount: Money,
        date: dt.date | None, payee: str | None, narration: str, note: str | None, caller: Caller, version: str | None,
    ) -> PendingChange:
        ledger_id = await self.resolve_ledger(ledger)
        from_account = await self._find(ledger_id, from_account, FUNDING_ROOTS)
        expense_account = await self._find(ledger_id, expense_account, ("Expenses",))
        kind, info = await self._kind(ledger_id, from_account)
        params = _clean({"expense_account": expense_account, "amount": amount, "date": date, "payee": payee, "narration": narration})
        recipe = "spend" if kind in CASH_KINDS else "purchase" if kind == "credit_card" else None
        if recipe:
            return await self.propose_action(ledger_id, from_account, recipe, params, note, caller, version)
        money = amount_of(amount, info.currencies, "amount")
        return await self._plain(ledger_id, date, payee, narration, [(expense_account, money.number), (from_account, -money.number)], money.currency, note, caller, version)

    async def income(
        self, ledger: str | None, to_account: str, income_account: str, amount: Money,
        date: dt.date | None, payee: str | None, narration: str, note: str | None, caller: Caller, version: str | None,
    ) -> PendingChange:
        ledger_id = await self.resolve_ledger(ledger)
        to_account = await self._find(ledger_id, to_account, FUNDING_ROOTS)
        income_account = await self._find(ledger_id, income_account, ("Income",))
        kind, info = await self._kind(ledger_id, to_account)
        if kind in CASH_KINDS:
            params = _clean({"from_account": income_account, "amount": amount, "date": date, "payee": payee, "narration": narration})
            return await self.propose_action(ledger_id, to_account, "receive", params, note, caller, version)
        money = amount_of(amount, info.currencies, "amount")
        return await self._plain(ledger_id, date, payee, narration, [(to_account, money.number), (income_account, -money.number)], money.currency, note, caller, version)

    async def transfer(
        self, ledger: str | None, from_account: str, to_account: str, amount: Money, received: Money | None,
        rate: Any, date: dt.date | None, narration: str, note: str | None, caller: Caller, version: str | None,
    ) -> PendingChange:
        ledger_id = await self.resolve_ledger(ledger)
        from_account = await self._find(ledger_id, from_account, FUNDING_ROOTS)
        to_account = await self._find(ledger_id, to_account, FUNDING_ROOTS)
        kind, info = await self._kind(ledger_id, from_account)
        if kind in CASH_KINDS:
            params = _clean({"to_account": to_account, "amount": amount, "received": received, "rate": rate, "date": date, "narration": narration})
            return await self.propose_action(ledger_id, from_account, "transfer", params, note, caller, version)
        if received is not None or rate is not None:
            raise RecipeError(f"{from_account} has no type with currency conversion, set its type to convert on transfer")
        money = amount_of(amount, info.currencies, "amount")
        return await self._plain(ledger_id, date, None, narration or "Transfer", [(to_account, money.number), (from_account, -money.number)], money.currency, note, caller, version)

    async def _plain(self, ledger_id, date, payee, narration, legs, currency, note, caller, version) -> PendingChange:
        transaction = TransactionInput(
            date=date or dt.date.today(),
            payee=payee,
            narration=narration,
            postings=[Posting(account=name, units=Amount(number=number, currency=currency)) for name, number in legs],
        )
        return await self.propose_operation(ledger_id, AddTransaction(transaction=transaction), note, caller, version)

    async def pending(self, ledger: str | None, status: ChangeStatus | None, caller: Caller) -> list[PendingChange]:
        """Proposed changes, restricted to this client's own so sessions do not see each other's drafts."""
        ledger_id = await self.resolve_ledger(ledger)
        changes = await self._changes.list(ledger_id, status)
        return [c for c in changes if c.caller.client_id == caller.client_id]

    async def withdraw(self, ledger: str | None, change_id: str, note: str | None) -> PendingChange:
        return await self._changes.withdraw(await self.resolve_ledger(ledger), change_id, note)

    async def reconcile(
        self, ledger: str | None, account: str, amount: Money, date: dt.date | None, pad_account: str | None,
        note: str | None, caller: Caller, version: str | None,
    ) -> PendingChange:
        ledger_id = await self.resolve_ledger(ledger)
        account = await self._find(ledger_id, account)
        if pad_account:
            pad_account = await self._find(ledger_id, pad_account, ("Equity", "Expenses", "Income"))
        _, info = await self._kind(ledger_id, account)
        money = amount_of(amount, info.currencies, "amount") if not isinstance(amount, Amount) else amount
        operation = Reconcile(account=account, date=date or dt.date.today(), amount=money, pad_account=pad_account)
        return await self.propose_operation(ledger_id, operation, note, caller, version)

    async def open_account(
        self, ledger: str | None, account: str, type: str | None, currencies: list[str], date: dt.date | None,
        note: str | None, caller: Caller, version: str | None,
    ) -> PendingChange:
        operation = OpenAccount(account=account, date=date or dt.date.today(), currencies=currencies, type=type)
        return await self.propose_operation(ledger, operation, note, caller, version)

    async def close_account(
        self, ledger: str | None, account: str, date: dt.date | None, note: str | None, caller: Caller, version: str | None
    ) -> PendingChange:
        ledger_id = await self.resolve_ledger(ledger)
        operation = CloseAccount(account=await self._find(ledger_id, account), date=date or dt.date.today())
        return await self.propose_operation(ledger_id, operation, note, caller, version)

    async def amend_transaction(
        self, ledger: str | None, transaction_id: str, date: dt.date | None, payee: str | None,
        narration: str | None, tags: list[str] | None, note: str | None, caller: Caller, version: str | None,
    ) -> PendingChange:
        """Change the descriptive fields of a recorded transaction. Its postings are left alone."""
        ledger_id = await self.resolve_ledger(ledger)
        changes: dict[str, Any] = {
            key: value for key, value in {"date": date, "narration": narration, "tags": tags}.items() if value is not None
        }
        if payee is not None:
            changes["payee"] = payee or None
        if not changes:
            raise RecipeError("say what to change: date, payee, narration or tags. To change amounts, delete it and record it again")
        current = await self._ledgers.get_transaction(ledger_id, transaction_id)
        transaction = TransactionInput(**{**current.model_dump(exclude={"id"}), **changes})
        operation = UpdateTransaction(id=transaction_id, transaction=transaction)
        return await self.propose_operation(ledger_id, operation, note, caller, version)

    async def delete_transaction(
        self, ledger: str | None, transaction_id: str, note: str | None, caller: Caller, version: str | None
    ) -> PendingChange:
        ledger_id = await self.resolve_ledger(ledger)
        await self._ledgers.get_transaction(ledger_id, transaction_id)
        return await self.propose_operation(ledger_id, DeleteTransaction(id=transaction_id), note, caller, version)


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    """Drop unset values and make the rest JSON-ready for the recipe's own validation."""
    return {
        key: to_jsonable_python(value) for key, value in params.items() if value is not None and value != ""
    }
