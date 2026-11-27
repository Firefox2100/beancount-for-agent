import datetime as dt
from enum import StrEnum
from typing import Literal

from typing import Any

from pydantic import Field, BaseModel, model_validator

from beancount_mcp.models.common import AccountName, Text
from beancount_mcp.models.operations import Operation


class ChangeStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Caller(BaseModel):
    """Who is making a request. Declared by the client, not authenticated."""

    actor: Literal["user", "agent"] = "user"
    client_id: str | None = None
    session_id: str | None = None


class ActionRequest(BaseModel):
    account: AccountName
    recipe: str
    params: dict[str, Any] = {}


class PendingChange(BaseModel):
    id: str
    ledger_id: str
    operation: Operation
    base_version: str
    status: ChangeStatus
    caller: Caller
    note: Text | None = None
    created_at: dt.datetime
    resolved_at: dt.datetime | None = None
    resolution_note: Text | None = None
    result_version: str | None = None
    target_fingerprint: str | None = None
    source: ActionRequest | None = None


class SubmitChangeRequest(BaseModel):
    """Either a concrete operation or a recipe action to compile into one."""

    operation: Operation | None = None
    action: ActionRequest | None = None
    note: Text | None = None
    receipts: list[str] = Field(default_factory=list, description="Stored receipts to attach to the transaction this records, by path.")

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.operation is None) == (self.action is None):
            raise ValueError("provide exactly one of operation or action")
        return self


class AmendChangeRequest(BaseModel):
    operation: Operation


class ResolveChangeRequest(BaseModel):
    note: Text | None = None
