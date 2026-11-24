from typing import Any

from fastapi import APIRouter

from beancount_mcp.api.deps import ActionServiceDep, CallerDep, ExpectedVersion, ProfileServiceDep
from beancount_mcp.models import KindInfo, Profile, ProfileView, RecipeInfo
from beancount_mcp.models.common import AccountName
from beancount_mcp.services.ledgers import WriteResult

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["actions"])


@router.get("/kinds")
async def list_kinds(ledger_id: str, service: ActionServiceDep) -> list[KindInfo]:
    """Account types to choose from when opening an account, with the recipes each one gets."""
    return service.list_kinds()


@router.get("/recipes")
async def list_recipes(
    ledger_id: str, service: ActionServiceDep, account: AccountName | None = None
) -> list[RecipeInfo]:
    return await service.list_recipes(ledger_id, account)


@router.post("/accounts/{account}/actions/{recipe_id}")
async def perform_action(
    ledger_id: str,
    account: AccountName,
    recipe_id: str,
    params: dict[str, Any],
    service: ActionServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> WriteResult:
    return await service.perform(ledger_id, account, recipe_id, params, caller, expected_version)


@router.get("/profile")
async def get_profile(ledger_id: str, service: ProfileServiceDep) -> ProfileView:
    return await service.get(ledger_id)


@router.put("/profile")
async def put_profile(
    ledger_id: str,
    profile: Profile,
    service: ProfileServiceDep,
    caller: CallerDep,
    expected_version: ExpectedVersion = None,
) -> ProfileView:
    return await service.put(ledger_id, profile, caller, expected_version)
