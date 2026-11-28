"""Turn a recipe written as data into a `Recipe` like any other.

A definition (`models/declarative.py`) becomes a pydantic parameter model, so agents see the same JSON schema as for a
built-in recipe, and a `compile` that builds one transaction. Nothing in a definition is evaluated: references are
looked up and amounts are copied or negated, so what is accepted from an agent cannot do anything but fill in a template.
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field, create_model

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AddTransaction, Operation, Posting, TransactionInput
from beancount_mcp.models.common import AccountName, Amount, Number, Tag, Text
from beancount_mcp.models.declarative import (
    REFERENCE,
    SIGNED_REFERENCE,
    TEMPLATE_FIELD,
    ParamSpec,
    RecipeDefinition,
    definition_problems,
)
from beancount_mcp.recipes.base import Recipe, RecipeContext
from beancount_mcp.recipes.helpers import Money, amount_of, negated, today


def problems(definition: RecipeDefinition, builtin_ids: set[str], recipe_id: str) -> list[str]:
    """Why this definition cannot be saved under this id. The structural checks run when it is parsed; these need context."""
    found = definition_problems(definition)
    if recipe_id in builtin_ids:
        found.append(f"{recipe_id} is the id of a built-in recipe; choose another")
    used = {m.group(1) for p in definition.postings for m in [REFERENCE.match(p.account)] if m}
    used |= {m.group(2) for p in definition.postings if p.amount for m in [SIGNED_REFERENCE.match(p.amount)] if m}
    for name in sorted(used):
        spec = definition.params.get(name)
        if spec is not None and not spec.required and spec.default is None:
            found.append(f"parameter {name} is optional but a posting needs it: make it required or give it a default")
    return found


def _field(name: str, spec: ParamSpec):
    kinds = {"account": AccountName, "amount": Money, "text": Text, "date": dt.date, "number": Number, "tags": list[Tag]}
    annotation = kinds[spec.type]
    description = spec.description or None
    if spec.type == "account" and spec.under:
        description = f"{description + '. ' if description else ''}An account under {', '.join(spec.under)}."
    if spec.required:
        return annotation, Field(..., description=description)
    if spec.default is not None:
        return annotation, Field(default=spec.default, description=description, validate_default=True)
    if spec.type == "date":
        return annotation, Field(default_factory=today, description=description or "Defaults to today.")
    if spec.type == "tags":
        return annotation, Field(default_factory=list, description=description)
    return annotation | None, Field(default=None, description=description)


def parameter_model(recipe_id: str, definition: RecipeDefinition) -> type[BaseModel]:
    fields = {name: _field(name, spec) for name, spec in definition.params.items()}
    if "date" not in fields:
        fields["date"] = (dt.date, Field(default_factory=today, description="Defaults to today."))
    return create_model(f"{recipe_id}_params", **fields)  # type: ignore[call-overload]


def _text(value) -> str:
    if isinstance(value, Amount):
        return f"{value.number} {value.currency}"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _fill(template: str | None, params: BaseModel) -> str | None:
    if template is None:
        return None
    return TEMPLATE_FIELD.sub(lambda m: _text(getattr(params, m.group(1), "")), template).strip()


def build(recipe_id: str, definition: RecipeDefinition) -> Recipe:
    model = parameter_model(recipe_id, definition)

    def compile_recipe(params: BaseModel, context: RecipeContext) -> Operation:
        postings = []
        for spec in definition.postings:
            reference = REFERENCE.match(spec.account)
            if spec.account == "@self":
                account = context.account
            elif reference:
                account = getattr(params, reference.group(1))
                allowed = definition.params[reference.group(1)].under
                if allowed and account.split(":")[0] not in allowed:
                    raise RecipeError(f"{reference.group(1)} must be an account under {', '.join(allowed)}, not {account}")
            else:
                account = spec.account
            context.require_open(account)
            units = None
            if spec.amount is not None:
                sign, name = SIGNED_REFERENCE.match(spec.amount).groups()  # type: ignore[union-attr]
                amount = amount_of(getattr(params, name), context.currencies(account), name)
                units = negated(amount) if sign else amount
            postings.append(Posting(account=account, units=units))
        return AddTransaction(
            transaction=TransactionInput(
                date=params.date,  # type: ignore[attr-defined]
                payee=_fill(definition.payee, params) or None,
                narration=_fill(definition.narration, params) or definition.title,
                tags=[*definition.tags, *(tag for name, spec in definition.params.items() if spec.type == "tags" for tag in getattr(params, name) or [])],
                postings=postings,
            )
        )

    return Recipe(
        id=recipe_id, title=definition.title, description=definition.description,
        kinds=frozenset(definition.kinds), params=model, compile=compile_recipe,
    )


def summary(definition: RecipeDefinition) -> list[str]:
    """The definition in plain lines, for a person to read before approving it."""
    lines = [f"for: {', '.join(definition.kinds)}"]
    for name, spec in definition.params.items():
        extra = [("required" if spec.required else f"optional, default {spec.default}" if spec.default else "optional")]
        if spec.under:
            extra.append("under " + "/".join(spec.under))
        lines.append(f"parameter {name} ({spec.type}; {'; '.join(extra)}){': ' + spec.description if spec.description else ''}")
    if definition.payee:
        lines.append(f"payee: {definition.payee}")
    lines.append(f"narration: {definition.narration or definition.title}")
    for posting in definition.postings:
        lines.append(f"posting: {posting.account}  {posting.amount if posting.amount else '(the rest)'}")
    return lines
