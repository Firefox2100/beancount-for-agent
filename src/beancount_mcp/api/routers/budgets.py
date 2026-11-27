"""Budgets: limits on expense groups and how spending is going. Only a user changes them."""

import datetime as dt

from fastapi import APIRouter, Response, status

from beancount_mcp.api.deps import CallerDep, ProfileServiceDep, ViewServiceDep
from beancount_mcp.models import ProfileView
from beancount_mcp.models.budgets import Budget, BudgetId, BudgetStatus, BudgetSuggestion

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["budgets"])


@router.get("/budgets")
async def list_budgets(ledger_id: str, service: ViewServiceDep, today: dt.date | None = None) -> list[BudgetStatus]:
    """Each budget's current period: spent, what remains, the pace and a projection. Over budget first."""
    return await service.budgets(ledger_id, today)


@router.get("/budgets/suggestions")
async def budget_suggestions(ledger_id: str, service: ViewServiceDep, today: dt.date | None = None) -> list[BudgetSuggestion]:
    """Monthly budgets suggested by the average of the last whole months, for expense groups that have none."""
    return await service.budget_suggestions(ledger_id, today)


@router.put("/budgets/{budget_id}")
async def set_budget(ledger_id: str, budget_id: BudgetId, budget: Budget, profiles: ProfileServiceDep, caller: CallerDep) -> ProfileView:
    return await profiles.set_budget(ledger_id, budget_id, budget, caller)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(ledger_id: str, budget_id: BudgetId, profiles: ProfileServiceDep, caller: CallerDep) -> Response:
    await profiles.set_budget(ledger_id, budget_id, None, caller)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
