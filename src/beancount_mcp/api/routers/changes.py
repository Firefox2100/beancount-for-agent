from typing import Annotated

from fastapi import APIRouter, Query, status

from beancount_mcp.api.deps import CallerDep, ChangeServiceDep, ExpectedVersion
from beancount_mcp.models import (
    AmendChangeRequest,
    ChangeStatus,
    PendingChange,
    ResolveChangeRequest,
    SubmitChangeRequest,
)

router = APIRouter(prefix="/ledgers/{ledger_id}/changes", tags=["changes"])


@router.get("")
async def list_changes(
    ledger_id: str,
    service: ChangeServiceDep,
    status_filter: Annotated[ChangeStatus | None, Query(alias="status")] = None,
) -> list[PendingChange]:
    return await service.list(ledger_id, status_filter)


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_change(
    ledger_id: str,
    request: SubmitChangeRequest,
    service: ChangeServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> PendingChange:
    return await service.submit(ledger_id, request.operation, caller, expected_version, request.note)


@router.get("/{change_id}")
async def get_change(ledger_id: str, change_id: str, service: ChangeServiceDep) -> PendingChange:
    return await service.get(ledger_id, change_id)


@router.put("/{change_id}")
async def amend_change(
    ledger_id: str, change_id: str, request: AmendChangeRequest, service: ChangeServiceDep
) -> PendingChange:
    return await service.amend(ledger_id, change_id, request.operation)


@router.post("/{change_id}/approve")
async def approve_change(
    ledger_id: str, change_id: str, request: ResolveChangeRequest, service: ChangeServiceDep
) -> PendingChange:
    return await service.approve(ledger_id, change_id, request.note)


@router.post("/{change_id}/reject")
async def reject_change(
    ledger_id: str, change_id: str, request: ResolveChangeRequest, service: ChangeServiceDep
) -> PendingChange:
    return await service.reject(ledger_id, change_id, request.note)


@router.post("/{change_id}/withdraw")
async def withdraw_change(
    ledger_id: str, change_id: str, request: ResolveChangeRequest, service: ChangeServiceDep
) -> PendingChange:
    return await service.withdraw(ledger_id, change_id, request.note)
