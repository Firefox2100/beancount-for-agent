"""The agent-facing REST surface: the same intent-shaped operations as the MCP tools, over HTTP.

For harness plugins that call tools natively instead of through MCP. It is a thin adapter on
`AgentService`, so a plugin gets the same account matching, recipe choice and lenient input as an
MCP client. Callers here are always agents: every write is a proposal, and nothing in this router
approves one. The ledger is an ordinary optional field, so a plugin can hold it in its own
session and keep it out of what the model sees.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from beancount_mcp.api.deps import AgentServiceDep
from beancount_mcp.models import (
    AccountBalance,
    AccountInfo,
    Caller,
    ChangeStatus,
    CreateLedgerRequest,
    KindInfo,
    LedgerInfo,
    PendingChange,
    RecipeInfo,
    Transaction,
)
from beancount_mcp.models.views import DueItem, FinancialPosition, OpenItems, PoolStatus, ReferenceRateStatus
from beancount_mcp.recipes.helpers import Money

router = APIRouter(prefix="/agent", tags=["agent"])

LedgerQuery = Annotated[str | None, Query(description="Ledger id. May be left out when there is exactly one.")]


def agent_caller(
    client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
    session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> Caller:
    """Always an agent, whatever `X-Actor` says: this surface can only propose."""
    return Caller(actor="agent", client_id=client_id or "agent-api", session_id=session_id)


AgentCaller = Annotated[Caller, Depends(agent_caller)]


class Proposal(BaseModel):
    ledger: str | None = Field(default=None, description="Ledger id. May be left out when there is exactly one.")
    note: str | None = Field(default=None, description="Why, for the person who approves it.")


class ExpenseRequest(Proposal):
    from_account: str
    expense_account: str
    amount: Money
    date: dt.date | None = None
    payee: str | None = None
    narration: str = ""


class IncomeRequest(Proposal):
    to_account: str
    income_account: str
    amount: Money
    date: dt.date | None = None
    payee: str | None = None
    narration: str = ""


class TransferRequest(Proposal):
    from_account: str
    to_account: str
    amount: Money
    received: Money | None = None
    rate: Decimal | None = None
    date: dt.date | None = None
    narration: str = ""


class ReconcileRequest(Proposal):
    account: str
    amount: Money
    date: dt.date | None = None
    pad_account: str | None = None


class OpenAccountRequest(Proposal):
    account: str
    type: str | None = None
    currencies: list[str] = Field(default_factory=list)
    date: dt.date | None = None


class CloseAccountRequest(Proposal):
    account: str
    date: dt.date | None = None


class ActionRequest(Proposal):
    account: str
    recipe: str
    params: dict[str, Any]


class AmendRequest(Proposal):
    date: dt.date | None = None
    payee: str | None = Field(default=None, description='Send "" to remove the payee.')
    narration: str | None = None
    tags: list[str] | None = None


class WithdrawRequest(Proposal):
    pass


@router.get("/ledgers")
async def list_ledgers(agent: AgentServiceDep) -> list[LedgerInfo]:
    return await agent.list_ledgers()


@router.post("/ledgers", status_code=201)
async def create_ledger(request: CreateLedgerRequest, agent: AgentServiceDep) -> LedgerInfo:
    return await agent.create_ledger(request)


@router.get("/account-types")
async def account_types(agent: AgentServiceDep) -> list[KindInfo]:
    return agent.account_types()


@router.get("/accounts")
async def accounts(agent: AgentServiceDep, ledger: LedgerQuery = None, include_closed: bool = False) -> list[AccountInfo]:
    """Accounts as an agent sees them: sensitive bank details are masked."""
    return await agent.accounts(ledger, include_closed)


@router.get("/balances")
async def balances(
    agent: AgentServiceDep, ledger: LedgerQuery = None, account: str | None = None, as_of: dt.date | None = None
) -> list[AccountBalance]:
    return await agent.balances(ledger, account, as_of)


@router.get("/transactions")
async def transactions(
    agent: AgentServiceDep,
    ledger: LedgerQuery = None,
    text: str | None = None,
    account: str | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
    tag: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Transaction]:
    return await agent.search(ledger, text, account, start, end, tag, limit)


@router.get("/recipes")
async def recipes(account: str, agent: AgentServiceDep, ledger: LedgerQuery = None) -> list[RecipeInfo]:
    return await agent.recipes(ledger, account)


@router.get("/open-items")
async def open_items(agent: AgentServiceDep, ledger: LedgerQuery = None, account: str | None = None) -> list[OpenItems]:
    return await agent.open_items(ledger, account)


@router.get("/due")
async def due(agent: AgentServiceDep, ledger: LedgerQuery = None, within_days: int | None = 14) -> list[DueItem]:
    return await agent.due(ledger, within_days)


@router.get("/credit-pools")
async def credit_pools(agent: AgentServiceDep, ledger: LedgerQuery = None) -> list[PoolStatus]:
    return await agent.pools(ledger)


@router.get("/financial-position")
async def financial_position(
    agent: AgentServiceDep,
    ledger: LedgerQuery = None,
    interval: str = Query(default="month", pattern="^(week|month)$"),
    points: int = Query(default=12, ge=1, le=12),
) -> FinancialPosition:
    return await agent.financial_position(ledger, interval, points)


@router.get("/reference-rates/status")
async def reference_rate_status(agent: AgentServiceDep) -> ReferenceRateStatus:
    return agent.reference_rate_status()


@router.get("/proposals")
async def proposals(
    agent: AgentServiceDep,
    caller: AgentCaller,
    ledger: LedgerQuery = None,
    status: ChangeStatus | None = ChangeStatus.PENDING,
) -> list[PendingChange]:
    """Proposals made by this client. Other clients' drafts are not shown."""
    return await agent.pending(ledger, status, caller)


@router.post("/proposals/{change_id}/withdraw")
async def withdraw(change_id: str, request: WithdrawRequest, agent: AgentServiceDep) -> PendingChange:
    return await agent.withdraw(request.ledger, change_id, request.note)


@router.post("/expenses", status_code=201)
async def record_expense(request: ExpenseRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    return await agent.expense(
        request.ledger, request.from_account, request.expense_account, request.amount, request.date,
        request.payee, request.narration, request.note, caller, None,
    )


@router.post("/income", status_code=201)
async def record_income(request: IncomeRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    return await agent.income(
        request.ledger, request.to_account, request.income_account, request.amount, request.date,
        request.payee, request.narration, request.note, caller, None,
    )


@router.post("/transfers", status_code=201)
async def record_transfer(request: TransferRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    return await agent.transfer(
        request.ledger, request.from_account, request.to_account, request.amount, request.received, request.rate,
        request.date, request.narration, request.note, caller, None,
    )


@router.post("/reconciliations", status_code=201)
async def reconcile(request: ReconcileRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    return await agent.reconcile(
        request.ledger, request.account, request.amount, request.date, request.pad_account, request.note, caller, None
    )


@router.post("/accounts/open", status_code=201)
async def open_account(request: OpenAccountRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    return await agent.open_account(
        request.ledger, request.account, request.type, request.currencies, request.date, request.note, caller, None
    )


@router.post("/accounts/close", status_code=201)
async def close_account(request: CloseAccountRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    return await agent.close_account(request.ledger, request.account, request.date, request.note, caller, None)


@router.post("/actions", status_code=201)
async def perform_action(request: ActionRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    """Propose a recipe action on an account. `params` follows the schema from `/agent/recipes`."""
    return await agent.propose_action(
        request.ledger, request.account, request.recipe, request.params, request.note, caller, None
    )


@router.post("/transactions/{transaction_id}/amend", status_code=201)
async def amend_transaction(
    transaction_id: str, request: AmendRequest, agent: AgentServiceDep, caller: AgentCaller
) -> PendingChange:
    """Propose correcting a recorded transaction's date, payee, narration or tags."""
    return await agent.amend_transaction(
        request.ledger, transaction_id, request.date, request.payee, request.narration, request.tags,
        request.note, caller, None,
    )


@router.post("/transactions/{transaction_id}/deletion", status_code=201)
async def delete_transaction(
    transaction_id: str, request: Proposal, agent: AgentServiceDep, caller: AgentCaller
) -> PendingChange:
    """Propose removing a recorded transaction."""
    return await agent.delete_transaction(request.ledger, transaction_id, request.note, caller, None)
