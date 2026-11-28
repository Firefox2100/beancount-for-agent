from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ValidationError

from beancount_mcp.api.deps import CallerDep, ExpectedVersion, LedgerServiceDep
from beancount_mcp.models import CreateLedgerRequest, LedgerInfo, LedgerStatus
from beancount_mcp.models.ledger import LedgerOptions
from beancount_mcp.models.operations import OptionName, SetOption
from beancount_mcp.services.ledgers import WriteResult

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


@router.get("/{ledger_id}/options")
async def get_options(ledger_id: str, service: LedgerServiceDep) -> LedgerOptions:
    """The ledger options this service can change: title, operating currencies, comma rendering and the booking method."""
    return await service.get_options(ledger_id)


class OptionUpdate(BaseModel):
    value: str
    remove: bool = False


@router.put("/{ledger_id}/options/{name}")
async def set_option(
    ledger_id: str, name: OptionName, update: OptionUpdate, service: LedgerServiceDep, caller: CallerDep, expected_version: ExpectedVersion = None
) -> WriteResult:
    """Set an option, or with `remove` clear it (for `operating_currency`, take that currency away)."""
    try:
        operation = SetOption(name=name, value=update.value, remove=update.remove)
    except ValidationError as error:
        raise HTTPException(422, "; ".join(e["msg"] for e in error.errors())) from None
    return await service.apply(ledger_id, operation, caller, expected_version)
