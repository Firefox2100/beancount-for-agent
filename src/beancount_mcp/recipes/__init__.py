from beancount_mcp.recipes import brokerage, cash, credit_card, loan, open_items
from beancount_mcp.recipes.registry import RecipeRegistry


def default_registry(load_plugins: bool = True) -> RecipeRegistry:
    registry = RecipeRegistry()
    for module in (cash, credit_card, loan, open_items, brokerage):
        module.register(registry)
    if load_plugins:
        registry.load_plugins()
    return registry
