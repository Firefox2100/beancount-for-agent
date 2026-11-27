from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """Something in the books worth a person's look. Nothing here changes the ledger."""

    kind: Literal["ledger_error", "overdrawn", "stale_balance", "uncategorised", "pending", "duplicate", "future", "unused"]
    severity: Literal["warning", "info"]
    title: str
    detail: str
    account: str | None = None
    transactions: list[str] = Field(default_factory=list, description="Ids of the transactions concerned.")
