"""Savings goals: a target held in some accounts, and how far along it is. Only a user changes them."""

import datetime as dt

from fastapi import APIRouter, Response, status

from beancount_mcp.api.deps import CallerDep, ProfileServiceDep, ViewServiceDep
from beancount_mcp.models import ProfileView
from beancount_mcp.models.goals import Goal, GoalId, GoalStatus

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["goals"])


@router.get("/goals")
async def list_goals(ledger_id: str, service: ViewServiceDep, today: dt.date | None = None) -> list[GoalStatus]:
    """Each goal with what is saved, what remains and, with a deadline, what to put aside each month. Behind first."""
    return await service.goals(ledger_id, today)


@router.put("/goals/{goal_id}")
async def set_goal(ledger_id: str, goal_id: GoalId, goal: Goal, profiles: ProfileServiceDep, caller: CallerDep) -> ProfileView:
    return await profiles.set_goal(ledger_id, goal_id, goal, caller)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(ledger_id: str, goal_id: GoalId, profiles: ProfileServiceDep, caller: CallerDep) -> Response:
    await profiles.set_goal(ledger_id, goal_id, None, caller)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
