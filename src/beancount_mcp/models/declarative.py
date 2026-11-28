"""Recipes written as data. A definition names its parameters and the postings they produce, and nothing else.

The format is deliberately small: a posting's account is `@self`, `$parameter` or a fixed account, and its amount is
`$parameter`, `-$parameter` or absent (the rest, so the entry balances). There are no operators, conditions or loops,
so a definition drafted by an agent cannot become a program.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from beancount_mcp.models.common import Text

KindName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
ParamName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
ParamType = Literal["account", "amount", "text", "date", "number", "tags"]
ROOTS = ("Assets", "Liabilities", "Equity", "Income", "Expenses")

REFERENCE = re.compile(r"^\$([a-z][a-z0-9_]{0,31})$")
SIGNED_REFERENCE = re.compile(r"^(-?)\$([a-z][a-z0-9_]{0,31})$")
TEMPLATE_FIELD = re.compile(r"\{([a-z][a-z0-9_]{0,31})\}")
FIXED_ACCOUNT = re.compile(r"^(Assets|Liabilities|Equity|Income|Expenses)(:[A-Z0-9][A-Za-z0-9\-]*)+$")
RESERVED = {"self"}


class ParamSpec(BaseModel):
    type: ParamType
    description: Text = Field(default="", description="What the person or agent should give. It becomes the parameter's description.")
    required: bool = True
    default: Text | None = Field(default=None, description="Used when the parameter is left out. Dates default to today when not required.")
    under: list[Literal["Assets", "Liabilities", "Equity", "Income", "Expenses"]] | None = Field(
        default=None, description="For an account: the account types it may be, such as [\"Expenses\"]."
    )

    @model_validator(mode="after")
    def _consistent(self):
        if self.under is not None and self.type != "account":
            raise ValueError("`under` only applies to an account parameter")
        if self.required and self.default is not None:
            raise ValueError("a parameter with a default is not required: set required to false")
        return self


class PostingSpec(BaseModel):
    account: str = Field(description='`@self` (the account the action is performed on), `$name` (an account parameter) or a fixed account name.')
    amount: str | None = Field(default=None, description="`$name` or `-$name` (an amount parameter), or absent for the rest of the entry.")

    @field_validator("account")
    @classmethod
    def _account(cls, value: str) -> str:
        if value == "@self" or REFERENCE.match(value) or FIXED_ACCOUNT.match(value):
            return value
        raise ValueError(f"{value!r} is not @self, a $parameter or a full account name such as Expenses:Fees")

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: str | None) -> str | None:
        if value is not None and not SIGNED_REFERENCE.match(value):
            raise ValueError(f"{value!r} must be $name or -$name: amounts are not calculated here")
        return value


class RecipeDefinition(BaseModel):
    """A recipe as data. Performing it turns a few parameters into one transaction."""

    title: Text
    description: Text
    kinds: list[KindName] = Field(min_length=1, description="The account types it can be performed on, such as [\"checking\"].")
    params: dict[ParamName, ParamSpec] = Field(default_factory=dict)
    payee: Text | None = Field(default=None, description="May use {name} for a text or account parameter.")
    narration: Text = Field(default="", description="May use {name} for a text, account, amount or number parameter.")
    tags: list[Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_\-/.]*$")]] = Field(default_factory=list)
    postings: list[PostingSpec] = Field(min_length=2)

    @model_validator(mode="after")
    def _well_formed(self):
        problems = definition_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def definition_problems(definition: RecipeDefinition) -> list[str]:
    """Everything wrong with a definition that its own fields cannot say. Empty when it is sound."""
    problems = []
    params = definition.params
    for name in params:
        if name in RESERVED:
            problems.append(f"{name} is reserved")
    if "date" in params and params["date"].type != "date":
        problems.append("`date` must be a date parameter, or left out (it defaults to today)")
    open_ended = 0
    for index, posting in enumerate(definition.postings, 1):
        account = REFERENCE.match(posting.account)
        if account and (account.group(1) not in params or params[account.group(1)].type != "account"):
            problems.append(f"posting {index}: {posting.account} is not an account parameter")
        if posting.amount is None:
            open_ended += 1
        else:
            reference = SIGNED_REFERENCE.match(posting.amount)
            if reference and (reference.group(2) not in params or params[reference.group(2)].type != "amount"):
                problems.append(f"posting {index}: {posting.amount} is not an amount parameter")
    if open_ended > 1:
        problems.append("at most one posting may leave out its amount (it takes the rest)")
    texts = {"payee": definition.payee, "narration": definition.narration}
    for label, text in texts.items():
        for field in TEMPLATE_FIELD.findall(text or ""):
            allowed = {"text", "account", "number"} | ({"amount"} if label == "narration" else set())
            if field not in params or params[field].type not in allowed:
                problems.append(f"{label} uses {{{field}}}, which is not a {'/'.join(sorted(allowed))} parameter")
    used = {m.group(1) for p in definition.postings for m in [REFERENCE.match(p.account)] if m}
    used |= {m.group(2) for p in definition.postings if p.amount for m in [SIGNED_REFERENCE.match(p.amount)] if m}
    if not any(param.type == "amount" for param in params.values()) and all(p.amount is not None for p in definition.postings):
        problems.append("a recipe with amounts needs an amount parameter")
    for name, spec in params.items():
        if spec.type in ("account", "amount") and name not in used and spec.required:
            problems.append(f"parameter {name} is required but never used")
    return problems
