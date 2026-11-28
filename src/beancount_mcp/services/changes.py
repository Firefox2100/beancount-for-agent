import asyncio

from types import SimpleNamespace

from beancount_mcp.ledger import profile_items, receipts
from beancount_mcp.ledger.profile import ProfileStore
from datetime import UTC, datetime

from beancount_mcp.ledger.engine import Ledger
from beancount_mcp.ledger.errors import (
    ChangeConflict,
    ChangeNotPending,
    RecipeError,
    VersionRequired,
)
from beancount_mcp.ledger.pending import PendingStore
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.services.actions import ActionService
from beancount_mcp.models import (
    ActionRequest,
    Caller,
    ChangeStatus,
    DeleteDirective,
    DeleteTransaction,
    Operation,
    PendingChange,
    SetProfileItem,
    SubmitChangeRequest,
    UpdateDirective,
    UpdateTransaction,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _target_id(operation: Operation) -> str | None:
    if isinstance(operation, UpdateTransaction | DeleteTransaction | UpdateDirective | DeleteDirective):
        return operation.id
    return None


class ChangeService:
    """Proposed changes: submit, amend, approve, reject and withdraw."""

    def __init__(self, store: LedgerStore, actions: ActionService, agent_approval_required: bool):
        self._store = store
        self._actions = actions
        self._agent_approval_required = agent_approval_required

    async def submit(
        self,
        ledger_id: str,
        request: SubmitChangeRequest,
        caller: Caller,
        expected_version: str | None,
    ) -> PendingChange:
        return await asyncio.to_thread(self._submit, ledger_id, request, caller, expected_version)

    async def get(self, ledger_id: str, change_id: str) -> PendingChange:
        return await asyncio.to_thread(lambda: self._pending(ledger_id).get(change_id))

    async def list(self, ledger_id: str, status: ChangeStatus | None) -> list[PendingChange]:
        return await asyncio.to_thread(lambda: self._pending(ledger_id).list(status))

    async def amend(self, ledger_id: str, change_id: str, operation: Operation) -> PendingChange:
        return await asyncio.to_thread(self._amend, ledger_id, change_id, operation)

    async def approve(self, ledger_id: str, change_id: str, note: str | None) -> PendingChange:
        return await asyncio.to_thread(self._approve, ledger_id, change_id, note)

    async def reject(self, ledger_id: str, change_id: str, note: str | None) -> PendingChange:
        return await asyncio.to_thread(self._close, ledger_id, change_id, ChangeStatus.REJECTED, note)

    async def withdraw(self, ledger_id: str, change_id: str, note: str | None) -> PendingChange:
        return await asyncio.to_thread(self._close, ledger_id, change_id, ChangeStatus.WITHDRAWN, note)

    def _pending(self, ledger_id: str) -> PendingStore:
        return PendingStore(self._store.open(ledger_id).root)

    def _submit(
        self,
        ledger_id: str,
        request: SubmitChangeRequest,
        caller: Caller,
        expected_version: str | None,
    ) -> PendingChange:
        if expected_version is None:
            raise VersionRequired("submit changes with the ledger version you last saw (If-Match)")
        ledger = self._store.open(ledger_id)
        operation, source = self._operation_of(ledger_id, request)
        if request.receipts:
            operation = receipts.attach(operation, request.receipts, ledger.root)
        store = PendingStore(ledger.root)
        profile_change = isinstance(operation, SetProfileItem)
        if profile_change:
            self._check_profile_item(operation)
        with ledger.lock:
            # A profile item changes how the ledger is treated, so it always waits for a person.
            auto_approve = caller.actor == "agent" and not self._agent_approval_required and not profile_change
            change = PendingChange(
                id=store.new_id(),
                ledger_id=ledger_id,
                operation=operation,
                base_version=expected_version,
                status=ChangeStatus.PENDING,
                caller=caller,
                note=request.note,
                source=source,
                created_at=_now(),
                target_fingerprint=_fingerprint(ledger, operation),
            )
            if auto_approve:
                applied = ledger.apply(operation, expected_version)
                change.status = ChangeStatus.APPROVED
                change.resolved_at = _now()
                change.result_version = applied.version
            elif not profile_change:
                ledger.apply(operation, expected_version, dry_run=True)
            store.save(change)
            return change

    def _check_profile_item(self, operation: SetProfileItem) -> None:
        """Refuse a change to the profile that could not be saved, so a person is never asked to approve it."""
        try:
            parsed = profile_items.parse(operation.item, operation.id, operation.value)
        except ValueError as error:
            raise RecipeError(str(error)) from None
        if operation.item == "recipe" and parsed is not None:
            self._actions.validate_definition(operation.id, parsed)

    def _operation_of(self, ledger_id: str, request: SubmitChangeRequest) -> tuple[Operation, ActionRequest | None]:
        if request.action is None:
            return request.operation, None
        action = request.action
        return self._actions.compile(ledger_id, action.account, action.recipe, action.params), action

    def _amend(self, ledger_id: str, change_id: str, operation: Operation) -> PendingChange:
        ledger = self._store.open(ledger_id)
        store = PendingStore(ledger.root)
        with ledger.lock:
            change = _require_pending(store.get(change_id))
            version = ledger.version()
            if isinstance(operation, SetProfileItem):
                self._check_profile_item(operation)
            else:
                ledger.apply(operation, version, dry_run=True)
            change.operation = operation
            change.base_version = version
            change.target_fingerprint = _fingerprint(ledger, operation)
            store.save(change)
            return change

    def _approve(self, ledger_id: str, change_id: str, note: str | None) -> PendingChange:
        ledger = self._store.open(ledger_id)
        store = PendingStore(ledger.root)
        with ledger.lock:
            change = _require_pending(store.get(change_id))
            if _fingerprint(ledger, change.operation) != change.target_fingerprint:
                raise ChangeConflict("the entry this change targets was modified or removed after it was proposed")
            if isinstance(change.operation, SetProfileItem):
                self._check_profile_item(change.operation)
                store_ = ProfileStore(ledger.root)
                profile, version = store_.load()
                parsed = profile_items.parse(change.operation.item, change.operation.id, change.operation.value)
                store_.save(profile_items.apply(profile, change.operation.item, change.operation.id, parsed), version)
                applied = SimpleNamespace(version=ledger.version())
            else:
                applied = ledger.apply(change.operation)
            change.status = ChangeStatus.APPROVED
            change.resolved_at = _now()
            change.resolution_note = note
            change.result_version = applied.version
            store.save(change)
            return change

    def _close(self, ledger_id: str, change_id: str, status: ChangeStatus, note: str | None) -> PendingChange:
        ledger = self._store.open(ledger_id)
        store = PendingStore(ledger.root)
        with ledger.lock:
            change = _require_pending(store.get(change_id))
            change.status = status
            change.resolved_at = _now()
            change.resolution_note = note
            store.save(change)
            return change


def _require_pending(change: PendingChange) -> PendingChange:
    if change.status is not ChangeStatus.PENDING:
        raise ChangeNotPending(f"change {change.id} is {change.status}")
    return change


def _fingerprint(ledger: Ledger, operation: Operation) -> str | None:
    target = _target_id(operation)
    return None if target is None else ledger.fingerprint(target)

