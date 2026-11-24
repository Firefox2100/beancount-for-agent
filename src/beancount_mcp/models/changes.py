import datetime as dt
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from beancount_mcp.models.common import Text
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


class SubmitChangeRequest(BaseModel):
    operation: Operation
    note: Text | None = None


class AmendChangeRequest(BaseModel):
    operation: Operation


class ResolveChangeRequest(BaseModel):
    note: Text | None = None
