"""The agent-facing REST surface: the same intent-shaped operations as the MCP tools, over HTTP.

For harness plugins that call tools natively instead of through MCP. It is a thin adapter on
`AgentService`, so a plugin gets the same account matching, recipe choice and lenient input as an
MCP client. Callers here are always agents: every write is a proposal, and nothing in this router
approves one. The ledger is an ordinary optional field, so a plugin can hold it in its own
session and keep it out of what the model sees.
"""

import datetime as dt
from typing import Annotated, Any, Literal

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
from beancount_mcp.models.common import Rate
from beancount_mcp.models.views import DueItem, FinancialPosition, OpenItems, PoolStatus, ReferenceRateStatus
from beancount_mcp.models.imports import ImportReview, ImportSummary
from beancount_mcp.models.receipts import ReceiptReading
from beancount_mcp.models.recurring import RecurringStatus, RecurringSuggestion
from beancount_mcp.models.budgets import BudgetStatus, BudgetSuggestion
from beancount_mcp.models.checks import Finding
from beancount_mcp.models.goals import GoalStatus
from beancount_mcp.models.reports import IncomeStatement
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
    receipt: str | None = Field(default=None, description="A receipt the user stored, by path or file name, to attach to the entry.")


class IncomeRequest(Proposal):
    to_account: str
    income_account: str
    amount: Money
    date: dt.date | None = None
    payee: str | None = None
    narration: str = ""
    receipt: str | None = Field(default=None, description="A receipt the user stored, by path or file name, to attach to the entry.")


class TransferRequest(Proposal):
    from_account: str
    to_account: str
    amount: Money
    received: Money | None = None
    rate: Rate | None = None
    date: dt.date | None = None
    narration: str = ""
    receipt: str | None = Field(default=None, description="A receipt the user stored, by path or file name, to attach to the entry.")


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
    receipt: str | None = Field(default=None, description="A receipt the user stored, by path or file name, to attach to the entry.")


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


@router.get("/imports")
async def imports(agent: AgentServiceDep, ledger: LedgerQuery = None) -> list[ImportSummary]:
    """Statements the user has uploaded, with how many of their lines are still new."""
    return await agent.imports(ledger)


@router.get("/imports/{import_id}")
async def import_review(
    import_id: str, agent: AgentServiceDep, ledger: LedgerQuery = None, only_new: bool = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> ImportReview:
    """One uploaded statement, each line marked new, already imported or a possible duplicate."""
    return await agent.import_review(ledger, import_id, only_new, limit)


@router.get("/reports/income-statement")
async def income_statement(
    agent: AgentServiceDep, ledger: LedgerQuery = None, start: dt.date | None = None, end: dt.date | None = None,
    account: str | None = None, depth: Annotated[int | None, Query(ge=1, le=8)] = None,
    interval: Literal["week", "month"] | None = None, compare: bool = False,
) -> IncomeStatement:
    """Income and expenses over a period (this month so far by default), by account. Drill into a group with `account`."""
    return await agent.income_statement(ledger, start, end, account, depth, interval, compare)


@router.get("/goals")
async def goals(agent: AgentServiceDep, ledger: LedgerQuery = None) -> list[GoalStatus]:
    """Savings goals: saved, remaining and, with a deadline, what to put aside each month. Behind first."""
    return await agent.goals(ledger)


@router.get("/checks")
async def checks(agent: AgentServiceDep, ledger: LedgerQuery = None, stale_days: Annotated[int, Query(ge=1, le=366)] = 45) -> list[Finding]:
    """Things in the books worth a look. Nothing here changes the ledger."""
    return await agent.checks(ledger, stale_days)


@router.get("/budgets")
async def budgets(agent: AgentServiceDep, ledger: LedgerQuery = None) -> list[BudgetStatus]:
    """Budgets with spent, remaining, pace and projection for the current period. Over budget first."""
    return await agent.budgets(ledger)


@router.get("/budgets/suggestions")
async def budget_suggestions(agent: AgentServiceDep, ledger: LedgerQuery = None) -> list[BudgetSuggestion]:
    """Budgets the history suggests for expense groups without one. Only the user can add a budget."""
    return await agent.budget_suggestions(ledger)


@router.get("/recurring")
async def recurring(
    agent: AgentServiceDep, ledger: LedgerQuery = None,
    within_days: Annotated[int, Query(ge=0, le=366)] = 14, lookback_days: Annotated[int, Query(ge=0, le=366)] = 45,
) -> list[RecurringStatus]:
    """Recurring items with what is overdue or coming up and not yet recorded."""
    return await agent.recurring(ledger, within_days, lookback_days)


@router.get("/recurring/suggestions")
async def recurring_suggestions(agent: AgentServiceDep, ledger: LedgerQuery = None) -> list[RecurringSuggestion]:
    """Repeating payments in the history that no recurring item covers. Only the user can add an item."""
    return await agent.recurring_suggestions(ledger)


@router.get("/capabilities")
async def capabilities(agent: AgentServiceDep) -> dict:
    """What this deployment lets an agent do beyond the basics, so a plugin shows only the tools that can work."""
    access = agent.receipt_access
    return {"receipts": {"text": access.text, "images": access.images}}


@router.get("/receipts/read")
async def read_receipt(receipt: str, agent: AgentServiceDep, ledger: LedgerQuery = None) -> ReceiptReading:
    """The text of a receipt the user stored, read on first use and kept. `receipt` is its path, its file name or the id of a transaction with one receipt."""
    reading, _ = await agent.read_receipt(ledger, receipt, with_pictures=False)
    return reading


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
    return await agent.reference_rate_status()


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
        request.payee, request.narration, request.note, caller, None, request.receipt,
    )


@router.post("/income", status_code=201)
async def record_income(request: IncomeRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    return await agent.income(
        request.ledger, request.to_account, request.income_account, request.amount, request.date,
        request.payee, request.narration, request.note, caller, None, request.receipt,
    )


@router.post("/transfers", status_code=201)
async def record_transfer(request: TransferRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    return await agent.transfer(
        request.ledger, request.from_account, request.to_account, request.amount, request.received, request.rate,
        request.date, request.narration, request.note, caller, None, request.receipt,
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


class ImportProposal(Proposal):
    categories: dict[int, str] = Field(default_factory=dict, description="Line number to the account on the other side of it.")
    default_account: str | None = Field(default=None, description="The other account for every line not in `categories`.")
    skip: list[int] = Field(default_factory=list, description="Line numbers to leave out.")
    include: list[int] = Field(default_factory=list, description="Line numbers to add although they look already entered.")
    assert_balance: bool = Field(default=False, description="Also assert the statement's closing balance the day after it ends.")


@router.post("/imports/{import_id}/proposal", status_code=201)
async def propose_import(import_id: str, request: ImportProposal, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    """Propose the new lines of a statement as one batch for the user to approve."""
    return await agent.propose_import(
        request.ledger, import_id, request.categories, request.default_account, request.skip, request.include,
        request.assert_balance, request.note, caller, None,
    )


class RecurringProposal(Proposal):
    amount: Money | None = Field(default=None, description="Required when the amount varies. Otherwise the item's own amount.")
    date: dt.date | None = Field(default=None, description="When it happened. Defaults to today.")
    due: dt.date | None = Field(default=None, description="Which occurrence it settles. Defaults to the earliest one not yet recorded.")


@router.post("/recurring/{item_id}/proposal", status_code=201)
async def propose_recurring(item_id: str, request: RecurringProposal, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    """Propose recording one occurrence of a recurring item."""
    return await agent.propose_recurring(request.ledger, item_id, request.amount, request.date, request.due, request.note, caller, None)


@router.post("/actions", status_code=201)
async def perform_action(request: ActionRequest, agent: AgentServiceDep, caller: AgentCaller) -> PendingChange:
    """Propose a recipe action on an account. `params` follows the schema from `/agent/recipes`."""
    return await agent.propose_action(
        request.ledger, request.account, request.recipe, request.params, request.note, caller, None, request.receipt
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
