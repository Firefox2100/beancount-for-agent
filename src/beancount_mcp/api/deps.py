from typing import Annotated, Literal

from fastapi import Depends, Header, Request

from beancount_mcp.models import Caller
from beancount_mcp.services.changes import ChangeService
from beancount_mcp.services.ledgers import LedgerService


def get_ledger_service(request: Request) -> LedgerService:
    return request.app.state.ledger_service


def get_change_service(request: Request) -> ChangeService:
    return request.app.state.change_service


def get_caller(
    actor: Annotated[Literal["user", "agent"], Header(alias="X-Actor")] = "user",
    client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
    session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> Caller:
    return Caller(actor=actor, client_id=client_id, session_id=session_id)


LedgerServiceDep = Annotated[LedgerService, Depends(get_ledger_service)]
ChangeServiceDep = Annotated[ChangeService, Depends(get_change_service)]
CallerDep = Annotated[Caller, Depends(get_caller)]

ExpectedVersion = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description="Ledger version the caller last saw; the write is refused if the ledger has moved on.",
    ),
]
