from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from beancount_mcp.api.deps import CallerDep, ExpectedVersion, LedgerServiceDep
from beancount_mcp.models import AddDirective, DeleteDirective, Directive, Record, RecordPage, UpdateDirective
from beancount_mcp.services.ledgers import WriteResult

router = APIRouter(prefix="/ledgers/{ledger_id}/directives", tags=["directives"])


@router.get("")
async def list_directives(
    ledger_id: str,
    service: LedgerServiceDep,
    kind: str | None = None,
    account: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecordPage:
    return await service.list_records(
        ledger_id, kind=kind, account=account, start=start, end=end, limit=limit, offset=offset
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_directive(
    ledger_id: str,
    directive: Directive,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    return await service.apply(ledger_id, AddDirective(directive=directive), caller, expected_version)


@router.get("/{record_id}")
async def get_directive(ledger_id: str, record_id: str, service: LedgerServiceDep) -> Record:
    return await service.get_record(ledger_id, record_id)


@router.put("/{record_id}")
async def update_directive(
    ledger_id: str,
    record_id: str,
    directive: Directive,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    operation = UpdateDirective(id=record_id, directive=directive)
    return await service.apply(ledger_id, operation, caller, expected_version)


@router.delete("/{record_id}")
async def delete_directive(
    ledger_id: str,
    record_id: str,
    service: LedgerServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    return await service.apply(ledger_id, DeleteDirective(id=record_id), caller, expected_version)
