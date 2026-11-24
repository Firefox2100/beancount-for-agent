import asyncio
from datetime import date

from pydantic import BaseModel

from beancount_mcp.ledger.errors import ApprovalRequired, TransactionNotFound
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models import (
    AccountBalance,
    AccountInfo,
    Caller,
    CreateLedgerRequest,
    LedgerInfo,
    LedgerStatus,
    Operation,
    Record,
    RecordPage,
    Transaction,
    TransactionPage,
)


class WriteResult(BaseModel):
    version: str
    transaction: Transaction | None = None
    record: Record | None = None
    account: AccountInfo | None = None


class LedgerService:
    def __init__(self, store: LedgerStore, agent_approval_required: bool = True):
        self._store = store
        self._agent_approval_required = agent_approval_required

    async def list_ledgers(self) -> list[LedgerInfo]:
        return await asyncio.to_thread(self._list_ledgers)

    async def create_ledger(self, request: CreateLedgerRequest) -> LedgerStatus:
        return await asyncio.to_thread(lambda: self._store.create(request).status())

    async def get_ledger(self, ledger_id: str) -> LedgerStatus:
        return await asyncio.to_thread(lambda: self._store.open(ledger_id).status())

    async def list_accounts(self, ledger_id: str) -> list[AccountInfo]:
        return await asyncio.to_thread(lambda: self._store.open(ledger_id).accounts())

    async def balances(self, ledger_id: str, as_of: date | None) -> list[AccountBalance]:
        return await asyncio.to_thread(lambda: self._store.open(ledger_id).balances(as_of))

    async def list_transactions(
        self,
        ledger_id: str,
        *,
        account: str | None = None,
        start: date | None = None,
        end: date | None = None,
        text: str | None = None,
        tag: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> TransactionPage:
        def run() -> TransactionPage:
            ledger = self._store.open(ledger_id)
            items = ledger.transactions(account=account, start=start, end=end, text=text, tag=tag)
            return TransactionPage(total=len(items), items=items[offset : offset + limit])

        return await asyncio.to_thread(run)

    async def get_transaction(self, ledger_id: str, transaction_id: str) -> Transaction:
        def run() -> Transaction:
            transaction = self._store.open(ledger_id).transaction(transaction_id)
            if transaction is None:
                raise TransactionNotFound(transaction_id)
            return transaction

        return await asyncio.to_thread(run)

    async def list_records(
        self,
        ledger_id: str,
        *,
        kind: str | None = None,
        account: str | None = None,
        start: date | None = None,
        end: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> RecordPage:
        def run() -> RecordPage:
            items = self._store.open(ledger_id).records(kind=kind, account=account, start=start, end=end)
            return RecordPage(total=len(items), items=items[offset : offset + limit])

        return await asyncio.to_thread(run)

    async def get_record(self, ledger_id: str, record_id: str) -> Record:
        def run() -> Record:
            record = self._store.open(ledger_id).record(record_id)
            if record is None:
                raise TransactionNotFound(record_id)
            return record

        return await asyncio.to_thread(run)

    async def apply(
        self,
        ledger_id: str,
        operation: Operation,
        caller: Caller,
        expected_version: str | None = None,
    ) -> WriteResult:
        """Commit a change at once. Agents must go through proposed changes instead."""
        if caller.actor == "agent" and self._agent_approval_required:
            raise ApprovalRequired("agent changes must be submitted for approval")
        return await asyncio.to_thread(self._apply, ledger_id, operation, expected_version)

    def _list_ledgers(self) -> list[LedgerInfo]:
        return [self._store.open(ledger_id).info() for ledger_id in self._store.list_ids()]

    def _apply(self, ledger_id: str, operation: Operation, expected_version: str | None) -> WriteResult:
        ledger = self._store.open(ledger_id)
        change = ledger.apply(operation, expected_version)
        transaction = ledger.transaction(change.transaction_id) if change.transaction_id else None
        account = None
        if change.account:
            account = next((a for a in ledger.accounts() if a.name == change.account), None)
        record = ledger.record(change.record_id) if change.record_id else None
        return WriteResult(version=change.version, transaction=transaction, account=account, record=record)
