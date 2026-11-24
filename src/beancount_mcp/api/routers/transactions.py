from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from beancount_mcp.api.deps import CallerDep, ExpectedVersion, LedgerServiceDep
from beancount_mcp.models import (
    AddTransaction,
    DeleteTransaction,
    Transaction,
    TransactionInput,
    TransactionPage,
    UpdateTransaction,
)
from beancount_mcp.services.ledgers import WriteResult

router = APIRouter(prefix="/ledgers/{ledger_id}/transactions", tags=["transactions"])


@router.get("")
async def list_transactions(
    ledger_id: str,
    service: LedgerServiceDep,
    account: str | None = None,
    start: date | None = None,
    end: date | None = None,
    text: str | None = None,
    tag: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    return await service.list_transactions(
        ledger_id, account=account, start=start, end=end, text=text, tag=tag, limit=limit, offset=offset
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_transaction(
    ledger_id: str,
    transaction: TransactionInput,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    return await service.apply(ledger_id, AddTransaction(transaction=transaction), caller, expected_version)


@router.get("/{transaction_id}")
async def get_transaction(ledger_id: str, transaction_id: str, service: LedgerServiceDep) -> Transaction:
    return await service.get_transaction(ledger_id, transaction_id)


@router.put("/{transaction_id}")
async def update_transaction(
    ledger_id: str,
    transaction_id: str,
    transaction: TransactionInput,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    operation = UpdateTransaction(id=transaction_id, transaction=transaction)
    return await service.apply(ledger_id, operation, caller, expected_version)


@router.delete("/{transaction_id}")
async def delete_transaction(
    ledger_id: str,
    transaction_id: str,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    return await service.apply(ledger_id, DeleteTransaction(id=transaction_id), caller, expected_version)
