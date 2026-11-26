"""Lenient account lookup for agents, so a small model can say "checking" and be understood."""

import difflib
import re
from collections.abc import Iterable
from typing import Any

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AccountInfo

MAX_CANDIDATES = 8


def resolve_account(
    accounts: Iterable[AccountInfo], query: str, roots: tuple[str, ...] | None = None
) -> str:
    """The one open account `query` means, or an error that lists what it might have meant.

    `roots` (such as `("Expenses",)`) narrows the search first, so "food" does not clash
    with an income account of the same name. If nothing under those roots fits, the whole
    chart is searched.
    """
    open_accounts = [a for a in accounts if a.close_date is None]
    wanted = query.strip()
    if roots:
        narrowed = [a for a in open_accounts if a.name.split(":")[0] in roots]
        found = _search(narrowed, wanted)
        if found:
            return _choose(found, wanted)
    found = _search(open_accounts, wanted)
    if found:
        return _choose(found, wanted)

    names = [a.name for a in open_accounts]
    similar = difflib.get_close_matches(wanted, names, n=5, cutoff=0.4)
    hint = f"Did you mean {', '.join(similar)}?" if similar else "Use list_accounts to see the open accounts."
    raise RecipeError(f"no open account matches '{wanted}'. {hint}")


def _choose(found: list[AccountInfo], wanted: str) -> str:
    if len(found) == 1:
        return found[0].name
    shown = ", ".join(a.name for a in found[:MAX_CANDIDATES])
    raise RecipeError(f"'{wanted}' matches several accounts: {shown}. Use the full name.")


def _search(accounts: list[AccountInfo], wanted: str) -> list[AccountInfo]:
    """Matches from the most to the least exact rule, stopping at the first rule that matches anything."""
    lowered = wanted.lower()
    tokens = [t for t in re.split(r"[\s:]+", lowered) if t]
    rules = (
        lambda a: a.name == wanted,
        lambda a: a.name.lower() == lowered,
        lambda a: a.name.lower().endswith(":" + lowered),
        lambda a: bool(tokens) and all(t in _haystack(a) for t in tokens),
    )
    for rule in rules:
        matched = [a for a in accounts if rule(a)]
        if matched:
            return matched
    return []


def _haystack(account: AccountInfo) -> str:
    return f"{account.name} {account.description or ''}".lower()


# Parameter names that imply a root, to settle names that exist under several (Expenses:Food, Income:Food).
_ROOTS_BY_KEY = {
    "expense_account": ("Expenses",),
    "fee_account": ("Expenses",),
    "tax_account": ("Expenses", "Liabilities"),
    "income_account": ("Income",),
    "gains_account": ("Income",),
}


def resolve_params(accounts: list[AccountInfo], value: Any) -> Any:
    """Resolve every account-valued field of recipe parameters, however deeply nested."""
    if isinstance(value, dict):
        return {
            key: resolve_account(accounts, item, _ROOTS_BY_KEY.get(key))
            if _is_account_key(key) and isinstance(item, str)
            else resolve_params(accounts, item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_params(accounts, item) for item in value]
    return value


def _is_account_key(key: str) -> bool:
    return key == "account" or key.endswith("_account")
