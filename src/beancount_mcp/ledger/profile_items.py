"""Changing one item of the profile: a recipe, a recurring item, a budget or a goal.

The same function serves a person editing directly and an approved proposal, so what an agent proposes and what a
person saves are validated by exactly the same models.
"""

from pydantic import BaseModel, TypeAdapter, ValidationError

from beancount_mcp.models import Profile
from beancount_mcp.models.budgets import Budget, BudgetId
from beancount_mcp.models.declarative import RecipeDefinition
from beancount_mcp.models.goals import Goal, GoalId
from beancount_mcp.models.profile import RecipeId
from beancount_mcp.models.recurring import Recurring, RecurringId

ITEMS: dict[str, tuple[type[BaseModel], object, str]] = {
    "recipe": (RecipeDefinition, RecipeId, "recipes"),
    "recurring": (Recurring, RecurringId, "recurring"),
    "budget": (Budget, BudgetId, "budgets"),
    "goal": (Goal, GoalId, "goals"),
}


def _reason(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" if e["loc"] else e["msg"] for e in error.errors())


def parse(item: str, item_id: str, value: dict | None) -> BaseModel | None:
    """The item as its model, or `None` to remove it. Raises `ValueError` with every problem, worded for whoever wrote it."""
    model, id_type, _ = ITEMS[item]
    try:
        TypeAdapter(id_type).validate_python(item_id)
    except ValidationError:
        raise ValueError(f"{item_id!r} is not a valid {item} id: lowercase letters, digits and underscores, starting with a letter") from None
    if value is None:
        return None
    try:
        return model.model_validate(value)
    except ValidationError as error:
        raise ValueError(f"the {item} is not valid: {_reason(error)}") from None


def apply(profile: Profile, item: str, item_id: str, parsed: BaseModel | None) -> Profile:
    collection = ITEMS[item][2]
    items = {key: value for key, value in getattr(profile, collection).items() if key != item_id}
    if parsed is not None:
        items[item_id] = parsed
    return profile.model_copy(update={collection: items})


def current(profile: Profile, item: str, item_id: str) -> BaseModel | None:
    return getattr(profile, ITEMS[item][2]).get(item_id)
