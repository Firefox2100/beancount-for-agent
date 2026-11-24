from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AccountInfo, AccountProfile, Operation


@dataclass(frozen=True)
class RecipeContext:
    """Read-only view of the ledger and profile a recipe compiles against."""

    account: str
    kind: str
    profile: AccountProfile
    accounts: Mapping[str, AccountInfo]
    balance: Callable[[str], dict[str, Decimal]]

    def currencies(self, account: str) -> list[str]:
        return list(self.require_open(account).currencies)

    def require_open(self, account: str) -> AccountInfo:
        info = self.accounts.get(account)
        if info is None or info.close_date is not None:
            raise RecipeError(f"account {account} is not open")
        return info


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    description: str
    kinds: frozenset[str]
    params: type[BaseModel]
    compile: Callable[[BaseModel, RecipeContext], Operation]
