"""What an importer is. Built-in readers and plugins implement the same small interface."""

import re
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation

from beancount_mcp.models.imports import Statement


class ImportFailed(ValueError):
    """The file is not something this importer can read. The message says why, for the person who uploaded it."""


class Importer(ABC):
    """Reads one kind of bank file into canonical statements.

    An importer only reads bytes and returns `Statement`s. It never touches the ledger, so a plugin cannot
    write anything: what comes out is reviewed, turned into a proposal and approved like any other change.

    `identify` must be cheap and must not raise. `parse` raises `ImportFailed` with a reason a person can act on.
    A statement's amounts are signed from the account holder's side: money in positive, money out negative.
    """

    id: str
    title: str

    @abstractmethod
    def identify(self, filename: str, data: bytes) -> bool: ...

    @abstractmethod
    def parse(self, data: bytes) -> list[Statement]: ...


_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def clean(text: str | None, limit: int = 300) -> str:
    """Single-line text without control characters, as the ledger accepts it."""
    return _CONTROL.sub(" ", text or "").strip()[:limit].strip()


def decode(data: bytes) -> str:
    """Bank files are UTF-8 or, from older systems, Windows-1252."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def number(text: str, what: str = "amount") -> Decimal:
    """A decimal from a bank file, which may use a comma as the decimal separator (`1234,56`)."""
    value = text.strip()
    if "," in value and "." not in value:
        value = value.replace(",", ".")
    else:
        value = value.replace(",", "")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ImportFailed(f"cannot read the {what} {text!r}") from None
    if not result.is_finite():
        raise ImportFailed(f"cannot read the {what} {text!r}")
    return result
