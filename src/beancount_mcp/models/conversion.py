from typing import Literal

from pydantic import BaseModel, Field


class Converted(BaseModel):
    """An amount in another currency, counted at today's rate. Approximate by nature: a reference, never an entry."""

    currency: str
    amount: str
    rate: str = Field(description="What one unit is worth in the target currency.")
    value: str
    source: Literal["reference", "ledger"] = Field(description="Reference rates from the provider, or the ledger's own price directives.")
