"""Recurring items: what is on a schedule, what is overdue, and patterns worth adding. Only a user changes the schedule."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from beancount_mcp.api.deps import CallerDep, ProfileServiceDep, ViewServiceDep
from beancount_mcp.models import ProfileView
from beancount_mcp.models.recurring import Recurring, RecurringId, RecurringStatus, RecurringSuggestion

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["recurring"])


@router.get("/recurring")
async def list_recurring(
    ledger_id: str, service: ViewServiceDep,
    within_days: Annotated[int, Query(ge=0, le=366)] = 14,
    lookback_days: Annotated[int, Query(ge=0, le=366)] = 45,
    today: dt.date | None = None,
) -> list[RecurringStatus]:
    """Each item with the occurrences not yet recorded: overdue ones, then those due within `within_days`."""
    return await service.recurring(ledger_id, within_days, lookback_days, today)


@router.get("/recurring/suggestions")
async def recurring_suggestions(ledger_id: str, service: ViewServiceDep, today: dt.date | None = None) -> list[RecurringSuggestion]:
    """Payments that repeat at a steady spacing in the history and are not covered by an item yet."""
    return await service.recurring_suggestions(ledger_id, today)


@router.put("/recurring/{item_id}")
async def set_recurring(ledger_id: str, item_id: RecurringId, item: Recurring, profiles: ProfileServiceDep, caller: CallerDep) -> ProfileView:
    return await profiles.set_recurring(ledger_id, item_id, item, caller)


@router.delete("/recurring/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring(ledger_id: str, item_id: RecurringId, profiles: ProfileServiceDep, caller: CallerDep) -> Response:
    await profiles.set_recurring(ledger_id, item_id, None, caller)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
