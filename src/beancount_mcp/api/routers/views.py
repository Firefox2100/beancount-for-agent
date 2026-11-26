import datetime as dt

from fastapi import APIRouter

from beancount_mcp.api.deps import ViewServiceDep
from beancount_mcp.models.common import AccountName
from beancount_mcp.models.views import DueItem, OpenItems, PoolStatus

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["views"])


@router.get("/open-items")
async def open_items(ledger_id: str, service: ViewServiceDep, account: AccountName | None = None) -> list[OpenItems]:
    """Unsettled claims, invoices, loans and bills, grouped by link. Without `account`, every receivable and payable."""
    return await service.open_items(ledger_id, account)


@router.get("/due")
async def due(
    ledger_id: str, service: ViewServiceDep, within_days: int | None = None, today: dt.date | None = None
) -> list[DueItem]:
    """Accounts with a statement or due day: what is owed and when. `within_days` keeps only those due soon with a balance."""
    return await service.due(ledger_id, within_days, today)


@router.get("/pools")
async def pools(ledger_id: str, service: ViewServiceDep, today: dt.date | None = None) -> list[PoolStatus]:
    """Shared credit limits: used and available, converting with the ledger's price directives."""
    return await service.pools(ledger_id, today)
