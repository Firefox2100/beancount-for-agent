import datetime as dt

from fastapi import APIRouter, Query

from beancount_mcp.api.deps import CallerDep, ViewServiceDep
from beancount_mcp.ledger.errors import ApprovalRequired
from beancount_mcp.models.common import AccountName
from beancount_mcp.models.views import DueItem, FinancialPosition, OpenItems, PoolStatus, ReferenceRateStatus

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


@router.get("/financial-position")
async def financial_position(
    ledger_id: str,
    service: ViewServiceDep,
    interval: str = Query(default="month", pattern="^(week|month)$"),
    points: int = Query(default=12, ge=1, le=12),
    today: dt.date | None = None,
) -> FinancialPosition:
    """Assets, liabilities and net position, with explicitly approximate reference valuations."""
    return await service.financial_position(ledger_id, interval, points, today)


@router.get("/reference-rates/status")
async def reference_rate_status(service: ViewServiceDep) -> ReferenceRateStatus:
    """Whether reference valuations are on and how fresh the cached rates are. The cache belongs to the service, not to this ledger."""
    return await service.reference_rate_status()


@router.post("/reference-rates/refresh")
async def refresh_reference_rates(ledger_id: str, service: ViewServiceDep, caller: CallerDep) -> ReferenceRateStatus:
    """Forget the cached rates, so the next valuation fetches fresh ones. The cache is shared by every ledger, and only the user may clear it."""
    if caller.actor == "agent":
        raise ApprovalRequired("reference rates are refreshed by the user")
    return await service.refresh_reference_rates(ledger_id)
