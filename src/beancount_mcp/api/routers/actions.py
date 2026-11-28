from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from beancount_mcp.api.deps import ActionServiceDep, CallerDep, ExpectedVersion, ProfileServiceDep
from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import KindInfo, Operation, Profile, ProfileView, RecipeInfo
from beancount_mcp.models.declarative import RecipeDefinition
from beancount_mcp.models.profile import RecipeId
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


class RecipePreviewRequest(BaseModel):
    definition: RecipeDefinition | None = Field(default=None, description="The definition to try. Left out, the saved one with this id is used.")
    account: AccountName
    params: dict[str, Any] = Field(default_factory=dict)


@router.get("/recipe-definitions")
async def list_recipe_definitions(ledger_id: str, profiles: ProfileServiceDep) -> dict[str, RecipeDefinition]:
    """The recipes this ledger defines as data, by id."""
    return (await profiles.get(ledger_id)).profile.recipes


@router.put("/recipe-definitions/{recipe_id}")
async def set_recipe_definition(
    ledger_id: str, recipe_id: RecipeId, definition: RecipeDefinition, profiles: ProfileServiceDep, caller: CallerDep
) -> ProfileView:
    """Add or replace a recipe written as data. Users only: it changes what agents can do on the ledger's accounts."""
    return await profiles.set_recipe(ledger_id, recipe_id, definition, caller)


@router.delete("/recipe-definitions/{recipe_id}", status_code=204)
async def delete_recipe_definition(ledger_id: str, recipe_id: RecipeId, profiles: ProfileServiceDep, caller: CallerDep) -> Response:
    await profiles.set_recipe(ledger_id, recipe_id, None, caller)
    return Response(status_code=204)


@router.post("/recipe-definitions/{recipe_id}/preview")
async def preview_recipe_definition(
    ledger_id: str, recipe_id: RecipeId, request: RecipePreviewRequest, service: ActionServiceDep, profiles: ProfileServiceDep
) -> Operation:
    """The transaction a definition would record for these parameters on this account. Nothing is saved or written."""
    definition = request.definition or (await profiles.get(ledger_id)).profile.recipes.get(recipe_id)
    if definition is None:
        raise RecipeError(f"no recipe {recipe_id} is saved: send its definition to preview it")
    return await service.preview(ledger_id, recipe_id, definition, request.account, request.params)
