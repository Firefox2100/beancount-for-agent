"""Facts about where an account lives at its bank, kept as metadata on the account's `open` line.

These identify an account for payments and statements. They never include anything that authorises
a payment (no CVV, PIN or password). Numbers are normalised on input, and the sensitive ones are
masked in what agents see (`masked`).
"""

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from beancount_mcp.models.common import Text



def _compact(value: str) -> str:
    return re.sub(r"[\s-]", "", value)


def _digits(low: int, high: int, name: str):
    def check(value: str) -> str:
        compact = _compact(value)
        if not compact.isdigit() or not low <= len(compact) <= high:
            raise ValueError(f"{name} must be {low}-{high} digits" if low != high else f"{name} must be {low} digits")
        return compact

    return check


def _sort_code(value: str) -> str:
    compact = _digits(6, 6, "sort code")(value)
    return f"{compact[0:2]}-{compact[2:4]}-{compact[4:6]}"


def _account_number(value: str) -> str:
    compact = _compact(value)
    if not re.fullmatch(r"[0-9A-Za-z]{4,34}", compact):
        raise ValueError("account number must be 4-34 letters or digits")
    return compact


def _iban(value: str) -> str:
    compact = _compact(value).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}", compact):
        raise ValueError("IBAN must be a country code, two check digits and up to 30 more characters")
    return compact


def _swift(value: str) -> str:
    compact = _compact(value).upper()
    if not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?", compact):
        raise ValueError("SWIFT/BIC must be 8 or 11 characters")
    return compact


def _expiry(value: str) -> str:
    match = re.fullmatch(r"\s*(0?[1-9]|1[0-2])\s*/\s*(\d{2}|\d{4})\s*", value)
    if not match:
        raise ValueError("expiry must look like 08/28")
    return f"{int(match[1]):02d}/{match[2][-2:]}"


class AccountDetails(BaseModel):
    """Every field is optional. Send only what you have."""

    model_config = ConfigDict(extra="forbid")

    bank_name: Annotated[Text, StringConstraints(max_length=120)] | None = None
    account_holder: Annotated[Text, StringConstraints(max_length=120)] | None = None
    branch: Annotated[Text, StringConstraints(max_length=120)] | None = Field(default=None, description="Branch name or address.")
    sort_code: Annotated[str, AfterValidator(_sort_code)] | None = Field(default=None, description="UK sort code, 6 digits.")
    account_number: Annotated[str, AfterValidator(_account_number)] | None = None
    routing_number: Annotated[str, AfterValidator(_digits(9, 9, "routing number"))] | None = Field(
        default=None, description="US ABA routing number, 9 digits."
    )
    iban: Annotated[str, AfterValidator(_iban)] | None = None
    swift_bic: Annotated[str, AfterValidator(_swift)] | None = Field(default=None, description="SWIFT/BIC, 8 or 11 characters.")
    card_number: Annotated[str, AfterValidator(_digits(12, 19, "card number"))] | None = None
    card_holder: Annotated[Text, StringConstraints(max_length=120)] | None = None
    card_expiry: Annotated[str, AfterValidator(_expiry)] | None = Field(default=None, description="MM/YY.")


DETAIL_FIELDS: tuple[str, ...] = tuple(AccountDetails.model_fields)
DetailName = Annotated[str, StringConstraints(pattern="^(" + "|".join(DETAIL_FIELDS) + ")$")]

SENSITIVE_FIELDS = frozenset({"sort_code", "account_number", "routing_number", "iban", "card_number", "card_expiry"})
"""Shown to agents only as a mask. The bank name, holder, branch and SWIFT code identify the account without exposing it."""


def meta_key(field: str) -> str:
    return field.replace("_", "-")


def to_meta(details: AccountDetails) -> dict[str, str]:
    """The ledger metadata for the fields that are set."""
    return {meta_key(name): value for name, value in details.model_dump(exclude_none=True).items()}


def from_meta(meta: dict) -> dict[str, str]:
    """The detail fields found in an `open` entry's metadata, keyed by field name."""
    return {name: str(meta[meta_key(name)]) for name in DETAIL_FIELDS if meta_key(name) in meta}


def masked(value: str, field: str) -> str:
    if field == "card_expiry":
        return "••/••"
    compact = _compact(value)
    keep = 2 if len(compact) <= 6 else 4
    return "••••" + compact[-keep:]


def for_agent(details: dict[str, str]) -> dict[str, str]:
    return {name: masked(value, name) if name in SENSITIVE_FIELDS else value for name, value in details.items()}


class AccountDetailsUpdate(BaseModel):
    """Fields to set, and fields to remove."""

    model_config = ConfigDict(extra="forbid")

    set: AccountDetails = Field(default_factory=AccountDetails)
    clear: list[DetailName] = Field(default_factory=list)
