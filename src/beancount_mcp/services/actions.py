import asyncio
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from beancount_mcp.ledger.engine import Ledger
from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.ledger.profile import ProfileStore
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models import AccountProfile, Caller, KindInfo, Operation, RecipeInfo
from beancount_mcp.models.declarative import RecipeDefinition
from beancount_mcp.recipes import declarative
from beancount_mcp.recipes.base import Recipe, RecipeContext
from beancount_mcp.recipes.registry import RecipeRegistry
from beancount_mcp.services.ledgers import LedgerService, WriteResult


class ActionService:
    """Lists the recipes an account supports and compiles them into operations."""

    def __init__(self, store: LedgerStore, registry: RecipeRegistry, ledgers: LedgerService):
        self._store = store
        self._registry = registry
        self._ledgers = ledgers

    async def list_recipes(self, ledger_id: str, account: str | None) -> list[RecipeInfo]:
        return await asyncio.to_thread(self._list_recipes, ledger_id, account)

    def list_kinds(self) -> list[KindInfo]:
        return [
            KindInfo(name=name, description=text, recipes=[r.id for r in self._registry.for_kind(name)])
            for name, text in self._registry.kinds().items()
        ]

    async def perform(
        self,
        ledger_id: str,
        account: str,
        recipe_id: str,
        params: dict[str, Any],
        caller: Caller,
        expected_version: str | None,
    ) -> WriteResult:
        operation = await asyncio.to_thread(self.compile, ledger_id, account, recipe_id, params)
        return await self._ledgers.apply(ledger_id, operation, caller, expected_version)

    def compile(self, ledger_id: str, account: str, recipe_id: str, params: dict[str, Any]) -> Operation:
        ledger = self._store.open(ledger_id)
        recipe, context = self._resolve(ledger, account, recipe_id)
        try:
            parsed = recipe.params.model_validate(params)
        except ValidationError as error:
            details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
            raise RecipeError(f"invalid parameters for {recipe_id}: {details}") from error
        return recipe.compile(parsed, context)

    def _registry_of(self, ledger: Ledger) -> RecipeRegistry:
        """The built-in recipes plus the ledger's own, defined as data in its profile."""
        definitions = ProfileStore(ledger.root).load()[0].recipes
        return self._registry.overlay(declarative.build(rid, definition) for rid, definition in definitions.items())

    def _list_recipes(self, ledger_id: str, account: str | None) -> list[RecipeInfo]:
        ledger = self._store.open(ledger_id)
        if account is None:
            recipes = self._registry_of(ledger).all()
        else:
            recipes = self._applicable(ledger, account)
        return [_describe(recipe) for recipe in recipes]

    def _applicable(self, ledger: Ledger, account: str) -> list[Recipe]:
        accounts = {info.name: info for info in ledger.accounts()}
        info = accounts.get(account)
        if info is None or info.close_date is not None:
            raise RecipeError(f"account {account} is not open")
        profile = ProfileStore(ledger.root).load()[0].accounts.get(account)
        allowed = profile.recipes if profile else None
        return self._registry_of(ledger).for_kind(info.type, allowed)

    def _resolve(self, ledger: Ledger, account: str, recipe_id: str) -> tuple[Recipe, RecipeContext]:
        recipe = self._registry_of(ledger).get(recipe_id)
        if recipe.id not in {r.id for r in self._applicable(ledger, account)}:
            raise RecipeError(f"recipe {recipe_id} is not available for {account}")
        return recipe, self._context(ledger, account)

    def _context(self, ledger: Ledger, account: str) -> RecipeContext:
        accounts = {info.name: info for info in ledger.accounts()}
        if account not in accounts:
            raise RecipeError(f"account {account} does not exist")
        profile = ProfileStore(ledger.root).load()[0]
        balances = {item.account: item.balances for item in ledger.balances(None)}

        def balance(name: str) -> dict[str, Decimal]:
            return {currency: Decimal(number) for currency, number in balances.get(name, {}).items()}

        return RecipeContext(
            account=account,
            kind=accounts[account].type or "",
            profile=profile.accounts.get(account) or AccountProfile(),
            accounts=accounts,
            balance=balance,
        )

    def validate_definition(self, recipe_id: str, definition: RecipeDefinition) -> None:
        """Refuse a definition that clashes with a built-in recipe or leaves a posting without what it needs."""
        found = declarative.problems(definition, {r.id for r in self._registry.all()}, recipe_id)
        if found:
            raise RecipeError(f"recipe {recipe_id} cannot be saved: " + "; ".join(found))

    async def preview(self, ledger_id: str, recipe_id: str, definition: RecipeDefinition, account: str, params: dict[str, Any]) -> Operation:
        """What a definition would record for these parameters on this account, without saving or writing anything."""
        return await asyncio.to_thread(self._preview, ledger_id, recipe_id, definition, account, params)

    def _preview(self, ledger_id: str, recipe_id: str, definition: RecipeDefinition, account: str, params: dict[str, Any]) -> Operation:
        self.validate_definition(recipe_id, definition)
        ledger = self._store.open(ledger_id)
        recipe = declarative.build(recipe_id, definition)
        info = next((a for a in ledger.accounts() if a.name == account), None)
        if info is None or info.close_date is not None:
            raise RecipeError(f"account {account} is not open")
        if info.type not in recipe.kinds:
            raise RecipeError(f"{recipe_id} is for {', '.join(sorted(recipe.kinds))} accounts, and {account} is {info.type or 'untyped'}")
        try:
            parsed = recipe.params.model_validate(params)
        except ValidationError as error:
            details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
            raise RecipeError(f"invalid parameters for {recipe_id}: {details}") from error
        operation = recipe.compile(parsed, self._context(ledger, account))
        ledger.apply(operation, dry_run=True)
        return operation


def _describe(recipe: Recipe) -> RecipeInfo:
    return RecipeInfo(
        id=recipe.id,
        title=recipe.title,
        description=recipe.description,
        kinds=sorted(recipe.kinds),
        params_schema=recipe.params.model_json_schema(),
    )
