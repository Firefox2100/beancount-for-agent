from fastapi import APIRouter, status

from beancount_mcp.api.deps import LedgerServiceDep
from beancount_mcp.models import CreateLedgerRequest, LedgerInfo, LedgerStatus

router = APIRouter(prefix="/ledgers", tags=["ledgers"])


@router.get("")
async def list_ledgers(service: LedgerServiceDep) -> list[LedgerInfo]:
    return await service.list_ledgers()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ledger(request: CreateLedgerRequest, service: LedgerServiceDep) -> LedgerStatus:
    return await service.create_ledger(request)


@router.get("/{ledger_id}")
async def get_ledger(ledger_id: str, service: LedgerServiceDep) -> LedgerStatus:
    return await service.get_ledger(ledger_id)
