import asyncio

from beancount_mcp.ledger.engine import Ledger
from beancount_mcp.ledger.errors import ApprovalRequired
from beancount_mcp.ledger.profile import ProfileStore
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models import Caller, Profile, ProfileView
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
        return warnings
