"""The curated MCP tool set.

Tools express intent (record an expense, perform a recipe) and never expose files.
Every write is proposed as a pending change that a human approves through the API,
so there is deliberately no approve or reject tool here.
"""

import datetime as dt
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from beancount_mcp.ledger.errors import ChangeRejected, LedgerStoreError
from beancount_mcp.models import (
    AccountBalance,
    AccountInfo,
    AddTransaction,
    Caller,
    ChangeStatus,
    CreateLedgerRequest,
    KindInfo,
    LedgerInfo,
    PendingChange,
    RecipeInfo,
    Transaction,
    TransactionInput,
)
from beancount_mcp.models.common import Rate
from beancount_mcp.models.views import DueItem, FinancialPosition, OpenItems, PoolStatus
from beancount_mcp.recipes.helpers import Money
from beancount_mcp.services.agent import AgentService

INSTRUCTIONS = """\
Manage the user's finances through a Beancount ledger. You never edit files.

Every change you make is proposed and waits for the user's approval; tell the user a
proposal was made and give its id. Start with list_accounts to see account names, types
and the recipes each supports. Prefer record_expense, record_income and record_transfer
for everyday events, and use list_recipes then perform_recipe for anything account-specific
such as card statements, loan repayments, reimbursements or trades. Amounts can be written
like "12.50 USD", or as a formula such as "18.65 + 6.60 + 7.40 GBP" (use + - * / and brackets):
the service works it out exactly, so never add up or convert numbers yourself. A `rate` can be
a formula too, such as 1 / 8.73. The `ledger` argument can be left out when only one ledger exists.
"""

Ledger = str | None
Note = str | None


def _tool_errors[**P, R](function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Report domain failures to the agent as readable tool errors."""

    @wraps(function)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await function(*args, **kwargs)
        except ChangeRejected as error:
            details = "; ".join(e.message for e in error.errors)
            raise ToolError(f"The ledger rejected this change: {details}") from error
        except LedgerStoreError as error:
            raise ToolError(str(error)) from error

    return wrapper


def _caller(context: Context) -> Caller:
    try:
        session = context.session_id
    except RuntimeError:
        session = None
    return Caller(actor="agent", client_id="mcp", session_id=session)


def create_mcp(agent: AgentService, raw_transactions: bool = False) -> FastMCP:
    mcp = FastMCP("beancount", instructions=INSTRUCTIONS)

    def tool(group: str, *, read_only: bool = False, extra_tags: tuple[str, ...] = ()):
        """Register a tool under a group tag, with annotations that tell clients whether it changes anything."""

        def register(function):
            return mcp.tool(
                _tool_errors(function),
                tags={group, *extra_tags},
                annotations={
                    "readOnlyHint": read_only,
                    "destructiveHint": False,
                    "openWorldHint": False,
                },
            )

        return register

    @tool("read", read_only=True)
    async def list_ledgers() -> list[LedgerInfo]:
        """List the ledgers, each with its current version."""
        return await agent.list_ledgers()

    @tool("admin")
    async def create_ledger(id: str, title: str | None = None, operating_currencies: list[str] | None = None) -> LedgerInfo:
        """Create a new ledger. The id becomes its folder name: lowercase letters, digits, - and _."""
        return await agent.create_ledger(
            CreateLedgerRequest(id=id, title=title, operating_currencies=operating_currencies or [])
        )

    @tool("read", read_only=True)
    async def list_account_types(ledger: Ledger = None) -> list[KindInfo]:
        """Account types that can be given when opening an account, with the recipes each one gets."""
        return agent.account_types()

    @tool("read", read_only=True)
    async def list_accounts(ledger: Ledger = None, include_closed: bool = False) -> list[AccountInfo]:
        """Accounts with their type, currencies, description and the recipe ids they support."""
        return await agent.accounts(ledger, include_closed)

    @tool("read", read_only=True)
    async def get_balances(ledger: Ledger = None, account: str | None = None, as_of: dt.date | None = None) -> list[AccountBalance]:
        """Balances per account and currency. `account` keeps that account and its sub-accounts."""
        return await agent.balances(ledger, account, as_of)

    @tool("read", read_only=True)
    async def get_financial_position(
        ledger: Ledger = None,
        interval: Literal["week", "month"] = "month",
        points: Annotated[int, Field(ge=1, le=12)] = 12,
    ) -> FinancialPosition:
        """Assets, liabilities and net position with original-currency amounts and approximate base-currency reference values. `interval` is week or month; `points` is at most 12."""
        return await agent.financial_position(ledger, interval, points)

    @tool("read", read_only=True)
    async def search_transactions(
        ledger: Ledger = None,
        text: str | None = None,
        account: str | None = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        tag: str | None = None,
        limit: int = 20,
    ) -> list[Transaction]:
        """Find transactions by text (payee, narration), account, date range or tag. Newest last."""
        return await agent.search(ledger, text, account, start, end, tag, limit)

    @tool("propose")
    async def record_expense(
        from_account: str,
        expense_account: str,
        amount: Money,
        ledger: Ledger = None,
        date: dt.date | None = None,
        payee: str | None = None,
        narration: str = "",
        note: Note = None,
        context: Context = None,
    ) -> PendingChange:
        """Propose an expense paid from a bank, cash, wallet or card account. The amount may be in another currency than the account's for accounts that support it."""
        return await agent.expense(ledger, from_account, expense_account, amount, date, payee, narration, note, _caller(context), None)

    @tool("propose")
    async def record_income(
        to_account: str,
        income_account: str,
        amount: Money,
        ledger: Ledger = None,
        date: dt.date | None = None,
        payee: str | None = None,
        narration: str = "",
        note: Note = None,
        context: Context = None,
    ) -> PendingChange:
        """Propose money received into an account from an income account. For pay with deductions use the `salary` recipe."""
        return await agent.income(ledger, to_account, income_account, amount, date, payee, narration, note, _caller(context), None)

    @tool("propose")
    async def record_transfer(
        from_account: str,
        to_account: str,
        amount: Money,
        ledger: Ledger = None,
        received: Money | None = None,
        rate: Rate | None = None,
        date: dt.date | None = None,
        narration: str = "",
        note: Note = None,
        context: Context = None,
    ) -> PendingChange:
        """Propose moving money between accounts. Across currencies give `received` (what arrived) or `rate` (received currency per unit sent)."""
        return await agent.transfer(ledger, from_account, to_account, amount, received, rate, date, narration, note, _caller(context), None)

    @tool("propose")
    async def reconcile_account(
        account: str,
        amount: Money,
        ledger: Ledger = None,
        date: dt.date | None = None,
        pad_account: str | None = None,
        note: Note = None,
        context: Context = None,
    ) -> PendingChange:
        """Propose a balance check against a bank statement. With `pad_account`, the difference is booked there (for example an adjustments expense)."""
        return await agent.reconcile(ledger, account, amount, date, pad_account, note, _caller(context), None)

    @tool("admin", extra_tags=("propose",))
    async def open_account(
        account: str,
        type: str | None = None,
        currencies: list[str] | None = None,
        ledger: Ledger = None,
        date: dt.date | None = None,
        note: Note = None,
        context: Context = None,
    ) -> PendingChange:
        """Propose opening an account such as Assets:Bank:Checking. `type` (see list_account_types) decides which recipes it gets."""
        return await agent.open_account(ledger, account, type, currencies or [], date, note, _caller(context), None)

    @tool("admin", extra_tags=("propose",))
    async def close_account(
        account: str, ledger: Ledger = None, date: dt.date | None = None, note: Note = None, context: Context = None
    ) -> PendingChange:
        """Propose closing an account."""
        return await agent.close_account(ledger, account, date, note, _caller(context), None)

    @tool("propose")
    async def amend_transaction(
        transaction_id: str,
        ledger: Ledger = None,
        date: dt.date | None = None,
        payee: str | None = None,
        narration: str | None = None,
        tags: list[str] | None = None,
        note: Note = None,
        context: Context = None,
    ) -> PendingChange:
        """Propose correcting a recorded transaction's date, payee, narration or tags (find its id with search_transactions). Send only what changes, and "" for payee to remove it. Amounts and accounts cannot be changed: delete the transaction and record it again."""
        return await agent.amend_transaction(ledger, transaction_id, date, payee, narration, tags, note, _caller(context), None)

    @tool("propose")
    async def delete_transaction(
        transaction_id: str, ledger: Ledger = None, note: Note = None, context: Context = None
    ) -> PendingChange:
        """Propose removing a recorded transaction that was wrong or recorded twice (find its id with search_transactions)."""
        return await agent.delete_transaction(ledger, transaction_id, note, _caller(context), None)

    @tool("recipe", read_only=True)
    async def list_recipes(account: str, ledger: Ledger = None) -> list[RecipeInfo]:
        """Actions available on an account (card statement, loan repayment, claim, trade and so on), with the parameters each takes."""
        return await agent.recipes(ledger, account)

    @tool("recipe", extra_tags=("propose",))
    async def perform_recipe(
        account: str,
        recipe: str,
        params: dict[str, Any],
        ledger: Ledger = None,
        note: Note = None,
        context: Context = None,
    ) -> PendingChange:
        """Propose a recipe action on an account. `params` follows the schema from list_recipes. The result shows the exact postings."""
        return await agent.propose_action(ledger, account, recipe, params, note, _caller(context), None)

    @tool("read", read_only=True)
    async def get_open_items(ledger: Ledger = None, account: str | None = None) -> list[OpenItems]:
        """Unsettled reimbursement claims, loans, invoices and bills, grouped by link."""
        return await agent.open_items(ledger, account)

    @tool("read", read_only=True)
    async def get_due(ledger: Ledger = None, within_days: int | None = 14) -> list[DueItem]:
        """Accounts with money due soon: amount owed, due date and autopay source."""
        return await agent.due(ledger, within_days)

    @tool("read", read_only=True)
    async def get_credit_pools(ledger: Ledger = None) -> list[PoolStatus]:
        """Shared credit limits with used and available credit."""
        return await agent.pools(ledger)

    @tool("read", read_only=True)
    async def list_my_proposals(
        ledger: Ledger = None, status: ChangeStatus | None = ChangeStatus.PENDING, context: Context = None
    ) -> list[PendingChange]:
        """Changes proposed through this connection and whether they were approved."""
        return await agent.pending(ledger, status, _caller(context))

    @tool("propose")
    async def withdraw_proposal(change_id: str, ledger: Ledger = None, note: Note = None) -> PendingChange:
        """Withdraw a pending proposal that is no longer wanted."""
        return await agent.withdraw(ledger, change_id, note)

    if raw_transactions:

        @tool("propose", extra_tags=("raw",))
        async def propose_transaction(
            transaction: TransactionInput, ledger: Ledger = None, note: Note = None, context: Context = None
        ) -> PendingChange:
            """Propose a raw transaction with explicit postings. Use only when no other tool or recipe fits."""
            return await agent.propose_operation(
                ledger, AddTransaction(transaction=transaction), note, _caller(context), None
            )

    return mcp
