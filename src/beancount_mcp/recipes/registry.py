from collections.abc import Callable, Iterable
from importlib.metadata import entry_points

from beancount_mcp.ledger.errors import RecipeNotFound
from beancount_mcp.recipes.base import Recipe

ENTRY_POINT_GROUP = "beancount_mcp.recipes"


class RecipeRegistry:
    def __init__(self) -> None:
        self._recipes: dict[str, Recipe] = {}
        self._kinds: dict[str, str] = {}

    def describe_kind(self, name: str, description: str) -> None:
        """Document an account type. Types need no declaration to be used; this is for discovery."""
        self._kinds[name] = description

    def kinds(self) -> dict[str, str]:
        return dict(sorted(self._kinds.items()))

    def register(self, recipe: Recipe) -> None:
        if recipe.id in self._recipes:
            raise ValueError(f"recipe {recipe.id} is already registered")
        self._recipes[recipe.id] = recipe

    def get(self, recipe_id: str) -> Recipe:
        try:
            return self._recipes[recipe_id]
        except KeyError:
            raise RecipeNotFound(recipe_id) from None

    def all(self) -> list[Recipe]:
        return sorted(self._recipes.values(), key=lambda recipe: recipe.id)

    def for_kind(self, kind: str | None, allowed: list[str] | None = None) -> list[Recipe]:
        recipes = [recipe for recipe in self.all() if kind in recipe.kinds]
        if allowed is not None:
            recipes = [recipe for recipe in recipes if recipe.id in allowed]
        return recipes

    def load_plugins(self, points: Iterable | None = None) -> None:
        """Let each installed plugin register its recipes.

        An entry point resolves to a callable that receives this registry.
        """
        for point in entry_points(group=ENTRY_POINT_GROUP) if points is None else points:
            register: Callable[[RecipeRegistry], None] = point.load()
            register(self)
