from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from beancount_mcp.api.deps import CallerDep, ExpectedVersion, LedgerServiceDep
from beancount_mcp.models import (
    AccountBalance,
    AccountInfo,
    CloseAccount,
    CloseAccountRequest,
    OpenAccount,
    OpenAccountRequest,
    SetAccountDetails,
    Reconcile,
    ReconcileRequest,
)
from beancount_mcp.ledger.errors import ApprovalRequired
from beancount_mcp.models import AccountDetailsUpdate
from beancount_mcp.models.common import AccountName
from beancount_mcp.services.ledgers import WriteResult

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["accounts"])


@router.get("/accounts")
async def list_accounts(ledger_id: str, service: LedgerServiceDep) -> list[AccountInfo]:
    return await service.list_accounts(ledger_id)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def open_account(
    ledger_id: str,
    request: OpenAccountRequest,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    operation = OpenAccount(**request.model_dump())
    return await service.apply(ledger_id, operation, caller, expected_version)


@router.put("/accounts/{account}/details")
async def set_account_details(
    ledger_id: str,
    account: AccountName,
    request: AccountDetailsUpdate,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    """Set or clear bank details. Only the user does this, so agents never handle the numbers."""
    if caller.actor == "agent":
        raise ApprovalRequired("account details are set by the user")
    operation = SetAccountDetails(account=account, set=request.set, clear=request.clear)
    return await service.apply(ledger_id, operation, caller, expected_version)


@router.post("/accounts/{account}/close")
async def close_account(
    ledger_id: str,
    account: AccountName,
    request: CloseAccountRequest,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    operation = CloseAccount(account=account, date=request.date)
    return await service.apply(ledger_id, operation, caller, expected_version)


@router.post("/accounts/{account}/reconcile", status_code=status.HTTP_201_CREATED)
async def reconcile_account(
    ledger_id: str,
    account: AccountName,
    request: ReconcileRequest,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    operation = Reconcile(account=account, **request.model_dump())
    return await service.apply(ledger_id, operation, caller, expected_version)


@router.get("/balances")
async def balances(
    ledger_id: str,
    service: LedgerServiceDep,
    as_of: Annotated[date | None, Query()] = None,
) -> list[AccountBalance]:
    return await service.balances(ledger_id, as_of)
