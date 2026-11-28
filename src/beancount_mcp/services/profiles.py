import asyncio

from beancount_mcp.ledger.engine import Ledger
from beancount_mcp.ledger import profile_items
from beancount_mcp.ledger.errors import ApprovalRequired, RecipeError
from beancount_mcp.ledger.profile import ProfileStore
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models import Caller, Profile, ProfileView
from beancount_mcp.models.budgets import Budget
from beancount_mcp.models.goals import Goal
from beancount_mcp.models.recurring import Recurring
from beancount_mcp.models.declarative import RecipeDefinition
from beancount_mcp.recipes import declarative
from beancount_mcp.recipes.registry import RecipeRegistry


class ProfileService:
    def __init__(self, store: LedgerStore, registry: RecipeRegistry):
        self._store = store
        self._registry = registry

    async def get(self, ledger_id: str) -> ProfileView:
        return await asyncio.to_thread(self._view, ledger_id)

    async def put(
        self, ledger_id: str, profile: Profile, caller: Caller, expected_version: str | None
    ) -> ProfileView:
        if caller.actor == "agent":
            raise ApprovalRequired("the profile can only be changed by the user")
        return await asyncio.to_thread(self._put, ledger_id, profile, expected_version)

    async def set_recurring(self, ledger_id: str, rid: str, item: Recurring | None, caller: Caller) -> ProfileView:
        """Add, replace or (with `None`) remove one recurring item. For users only, like the rest of the profile."""
        if caller.actor == "agent":
            raise ApprovalRequired("recurring items are set by the user")

        def run() -> ProfileView:
            ledger = self._store.open(ledger_id)
            store = ProfileStore(ledger.root)
            profile, version = store.load()
            recurring = {k: v for k, v in profile.recurring.items() if k != rid}
            if item is not None:
                recurring[rid] = item
            store.save(profile.model_copy(update={"recurring": recurring}), version)
            return self._view(ledger_id)

        return await asyncio.to_thread(run)

    async def set_budget(self, ledger_id: str, bid: str, budget: Budget | None, caller: Caller) -> ProfileView:
        """Add, replace or (with `None`) remove one budget. For users only, like the rest of the profile."""
        if caller.actor == "agent":
            raise ApprovalRequired("budgets are set by the user")

        def run() -> ProfileView:
            store = ProfileStore(self._store.open(ledger_id).root)
            profile, version = store.load()
            budgets = {k: v for k, v in profile.budgets.items() if k != bid}
            if budget is not None:
                budgets[bid] = budget
            store.save(profile.model_copy(update={"budgets": budgets}), version)
            return self._view(ledger_id)

        return await asyncio.to_thread(run)

    async def set_recipe(self, ledger_id: str, rid: str, definition: RecipeDefinition | None, caller: Caller) -> ProfileView:
        """Add, replace or (with `None`) remove one recipe defined as data. For users only: it changes what agents can do."""
        if caller.actor == "agent":
            raise ApprovalRequired("recipes are defined by the user")
        if definition is not None:
            found = declarative.problems(definition, {r.id for r in self._registry.all()}, rid)
            if found:
                raise RecipeError(f"recipe {rid} cannot be saved: " + "; ".join(found))

        def run() -> ProfileView:
            store = ProfileStore(self._store.open(ledger_id).root)
            profile, version = store.load()
            store.save(profile_items.apply(profile, "recipe", rid, definition), version)
            return self._view(ledger_id)

        return await asyncio.to_thread(run)

    async def set_goal(self, ledger_id: str, gid: str, goal: Goal | None, caller: Caller) -> ProfileView:
        """Add, replace or (with `None`) remove one goal. For users only, like the rest of the profile."""
        if caller.actor == "agent":
            raise ApprovalRequired("goals are set by the user")

        def run() -> ProfileView:
            store = ProfileStore(self._store.open(ledger_id).root)
            profile, version = store.load()
            goals = {k: v for k, v in profile.goals.items() if k != gid}
            if goal is not None:
                goals[gid] = goal
            store.save(profile.model_copy(update={"goals": goals}), version)
            return self._view(ledger_id)

        return await asyncio.to_thread(run)

    def _put(self, ledger_id: str, profile: Profile, expected_version: str | None) -> ProfileView:
        ledger = self._store.open(ledger_id)
        ProfileStore(ledger.root).save(profile, expected_version)
        return self._view(ledger_id)

    def _view(self, ledger_id: str) -> ProfileView:
        ledger = self._store.open(ledger_id)
        profile, version = ProfileStore(ledger.root).load()
        return ProfileView(profile=profile, version=version, warnings=self._warnings(ledger, profile))

    def _warnings(self, ledger: Ledger, profile: Profile) -> list[str]:
        open_accounts = {info.name for info in ledger.accounts() if info.close_date is None}
        known_recipes = {recipe.id for recipe in self._registry.all()}
        warnings = []
        for name, account in profile.accounts.items():
            if name not in open_accounts:
                warnings.append(f"{name}: account is not open")
            for referenced in (
                account.autopay_from,
                account.unbilled_account,
                account.interest_account,
                account.cash_account,
                account.gains_account,
            ):
                if referenced and referenced not in open_accounts:
                    warnings.append(f"{name}: {referenced} is not open")
            if account.pool and account.pool not in profile.pools:
                warnings.append(f"{name}: pool {account.pool} is not defined")
            for recipe in account.recipes or []:
                if recipe not in known_recipes:
                    warnings.append(f"{name}: unknown recipe {recipe}")
        for rid, item in profile.recurring.items():
            for referenced in (item.from_account, item.to_account):
                if referenced not in open_accounts:
                    warnings.append(f"recurring {rid}: {referenced} is not open")
        for bid, budget in profile.budgets.items():
            if not any(name == budget.account or name.startswith(budget.account + ":") for name in open_accounts):
                warnings.append(f"budget {bid}: no open account under {budget.account}")
        for rid, definition in profile.recipes.items():
            for message in declarative.problems(definition, {r.id for r in self._registry.all()}, rid):
                warnings.append(f"recipe {rid}: {message}")
            for posting in definition.postings:
                if posting.account.startswith(("Assets", "Liabilities", "Equity", "Income", "Expenses")) and posting.account not in open_accounts:
                    warnings.append(f"recipe {rid}: {posting.account} is not open")
        for gid, goal in profile.goals.items():
            for name in goal.accounts:
                if not any(open_name == name or open_name.startswith(name + ":") for open_name in open_accounts):
                    warnings.append(f"goal {gid}: no open account under {name}")
        return warnings
