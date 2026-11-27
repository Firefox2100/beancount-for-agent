"""Bank statements: uploaded by a person, matched against the ledger, and proposed as one batch.

Importers (`beancount_mcp.imports`) only read files. This service is where a statement meets the ledger: it
checks the file against the account, marks which lines the ledger already has, and builds the proposal. An agent
may review a statement and propose from it, but only a person can upload or delete one, because a file is the
one thing in this flow that did not pass through the approval gate.
"""

import asyncio
import datetime as dt
import re
from decimal import Decimal

from beancount_mcp.imports.base import ImportFailed
from beancount_mcp.imports.registry import ImporterRegistry
from beancount_mcp.ledger.errors import ImportRefused, RecipeError
from beancount_mcp.ledger.imports import ImportStore
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models import (
    AddTransaction,
    Batch,
    Caller,
    PendingChange,
    Posting,
    Reconcile,
    SubmitChangeRequest,
    TransactionInput,
)
from beancount_mcp.models.common import Amount
from beancount_mcp.models.imports import (
    FormatInfo,
    ImportReview,
    ImportSummary,
    LineStatus,
    ReviewedLine,
    Statement,
    StatementImport,
)
from beancount_mcp.services.changes import ChangeService
from beancount_mcp.services.ledgers import LedgerService

# A transaction typed in by hand is rarely dated exactly as the bank dated it.
MATCH_DAYS = 2
BANK_REFERENCE = "bank-ref"


def _compact(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


class ImportService:
    def __init__(
        self,
        store: LedgerStore,
        ledgers: LedgerService,
        changes: ChangeService,
        importers: ImporterRegistry,
        max_bytes: int,
    ):
        self._store = store
        self._ledgers = ledgers
        self._changes = changes
        self._importers = importers
        self._max_bytes = max_bytes

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def formats(self) -> list[FormatInfo]:
        return [FormatInfo(id=i.id, title=i.title) for i in self._importers.all()]

    def _items(self, ledger_id: str) -> ImportStore:
        return ImportStore(self._store.open(ledger_id).root)

    async def upload(self, ledger_id: str, account: str, filename: str, data: bytes, format_id: str | None) -> list[StatementImport]:
        """Read a file for one account. A file holding several statements becomes several imports."""
        if len(data) > self._max_bytes:
            raise ImportRefused(f"the file is {len(data):,} bytes; at most {self._max_bytes:,} are accepted")
        accounts = {a.name: a for a in await self._ledgers.list_accounts(ledger_id)}
        info = accounts.get(account)
        if info is None or info.close_date is not None:
            raise ImportRefused(f"{account} is not an open account of this ledger")
        try:
            importer = self._importers.get(format_id) if format_id else self._importers.find(filename, data)
            statements = await asyncio.to_thread(importer.parse, data)
        except ImportFailed as error:
            raise ImportRefused(str(error)) from None
        except Exception as error:  # a plugin that crashes is reported, not allowed to take the service down
            raise ImportRefused(f"the {importer.title} importer failed on this file: {error}") from None
        saved = []
        items = self._items(ledger_id)
        for statement in statements:
            if not statement.lines:
                raise ImportRefused("the statement has no transactions")
            statement = statement.model_copy(update={"lines": [line.model_copy(update={"number": n}) for n, line in enumerate(statement.lines, 1)]})
            item = StatementImport(
                id=items.new_id(), filename=filename, account=account, created_at=dt.datetime.now(dt.UTC),
                statement=statement, warnings=self._warnings(statement, info),
            )
            items.save(item)
            saved.append(item)
        return saved

    @staticmethod
    def _warnings(statement: Statement, info) -> list[str]:
        found = []
        if info.currencies and statement.currency not in info.currencies:
            found.append(f"the statement is in {statement.currency} but {info.name} holds {', '.join(info.currencies)}")
        known = [_compact(v) for k, v in info.details.items() if k in ("iban", "account_number") and v]
        theirs = _compact(statement.account_id or "")
        if known and theirs and not any(theirs.endswith(k) or k.endswith(theirs) for k in known):
            found.append(f"the file names account {statement.account_id}, which is not the one recorded for {info.name}")
        if statement.opening_balance is not None and statement.closing_balance is not None:
            expected = statement.opening_balance + sum((line.amount for line in statement.lines), Decimal(0))
            if expected != statement.closing_balance:
                found.append(
                    f"the lines add up to {expected:,}, but the statement closes at {statement.closing_balance:,}: "
                    "some transactions may be missing or duplicated in the file"
                )
        return found

    async def summaries(self, ledger_id: str) -> list[ImportSummary]:
        items = await asyncio.to_thread(lambda: self._items(ledger_id).list())
        return [await self._summary(ledger_id, item, await self._statuses(ledger_id, item)) for item in items]

    async def delete(self, ledger_id: str, import_id: str) -> None:
        await asyncio.to_thread(lambda: self._items(ledger_id).delete(import_id))

    async def review(self, ledger_id: str, import_id: str, only_new: bool = False, limit: int = 200) -> ImportReview:
        item = await asyncio.to_thread(lambda: self._items(ledger_id).get(import_id))
        statuses = await self._statuses(ledger_id, item)
        lines = [ReviewedLine(**line.model_dump(), status=statuses[line.number][0], matches=statuses[line.number][1]) for line in item.statement.lines]
        shown = [line for line in lines if not only_new or line.status is LineStatus.NEW]
        summary = await self._summary(ledger_id, item, statuses)
        return ImportReview(
            **summary.model_dump(), opening_balance=item.statement.opening_balance, closing_balance=item.statement.closing_balance,
            items=shown[:limit], omitted=max(len(shown) - limit, 0),
        )

    async def _summary(self, ledger_id: str, item: StatementImport, statuses) -> ImportSummary:
        statement = item.statement
        return ImportSummary(
            id=item.id, filename=item.filename, account=item.account, format=statement.format, currency=statement.currency,
            start=statement.start or min(line.date for line in statement.lines),
            end=statement.end or max(line.date for line in statement.lines),
            lines=len(statement.lines), new=sum(1 for status, _ in statuses.values() if status is LineStatus.NEW),
            warnings=item.warnings, change_ids=item.change_ids,
        )

    async def _statuses(self, ledger_id: str, item: StatementImport) -> dict[int, tuple[LineStatus, str | None]]:
        """Each line's status: already in the ledger by the bank's id, plausibly entered by hand, or new."""
        lines = item.statement.lines
        window = dt.timedelta(days=MATCH_DAYS)
        page = await self._ledgers.list_transactions(
            ledger_id, account=item.account, start=min(l.date for l in lines) - window,
            end=max(l.date for l in lines) + window, limit=100_000,
        )
        currency = item.statement.currency
        references: dict[str, str] = {}
        candidates: list[tuple[dt.date, Decimal, str]] = []
        for transaction in page.items:
            posted = sum((p.units.number for p in transaction.postings if p.account == item.account and p.units and p.units.currency == currency), Decimal(0))
            if transaction.meta.get(BANK_REFERENCE):
                references[transaction.meta[BANK_REFERENCE]] = transaction.id
            else:
                candidates.append((transaction.date, posted, transaction.id))
        used: set[str] = set()
        result: dict[int, tuple[LineStatus, str | None]] = {}
        for line in lines:
            if line.reference and line.reference in references:
                result[line.number] = (LineStatus.IMPORTED, references[line.reference])
                continue
            match = next((c for c in candidates if c[2] not in used and c[1] == line.amount and abs(c[0] - line.date) <= window), None)
            if match is not None:
                used.add(match[2])
                result[line.number] = (LineStatus.POSSIBLE_DUPLICATE, match[2])
            else:
                result[line.number] = (LineStatus.NEW, None)
        return result

    async def propose(
        self,
        ledger_id: str,
        import_id: str,
        categories: dict[int, str],
        default_account: str | None,
        skip: list[int],
        include: list[int],
        assert_balance: bool,
        note: str | None,
        caller: Caller,
        version: str | None,
    ) -> PendingChange:
        """One batch of transactions for the lines that are new, with the other side of each given by the caller.

        Lines already in the ledger, or that look hand-entered, are left out unless named in `include`.
        """
        items = await asyncio.to_thread(lambda: self._items(ledger_id))
        item = await asyncio.to_thread(items.get, import_id)
        statement = item.statement
        statuses = await self._statuses(ledger_id, item)
        unknown = sorted((set(categories) | set(skip) | set(include)) - {line.number for line in statement.lines})
        if unknown:
            raise RecipeError(f"the statement has no line {', '.join(map(str, unknown))} (lines run from 1 to {len(statement.lines)})")
        chosen = [
            line for line in statement.lines
            if line.number not in skip and (statuses[line.number][0] is LineStatus.NEW or line.number in include)
        ]
        if not chosen:
            raise RecipeError("nothing to import: every line is already in the ledger or skipped (name a line in `include` to add it anyway)")
        missing = [line.number for line in chosen if line.number not in categories and default_account is None]
        if missing:
            shown = ", ".join(map(str, missing[:15])) + (" ..." if len(missing) > 15 else "")
            raise RecipeError(f"no account for line {shown}: give each one in `categories`, or pass `default_account` for the rest")
        operations: list = []
        for line in chosen:
            other = categories.get(line.number, default_account)
            units = Amount(number=line.amount, currency=statement.currency)
            meta = {"import": import_id[:8]}
            if line.reference:
                meta[BANK_REFERENCE] = line.reference
            transaction = TransactionInput(
                date=line.date, payee=line.payee, narration=line.description or "Imported", meta=meta,
                postings=[
                    Posting(account=item.account, units=units),
                    Posting(account=other, units=Amount(number=-line.amount, currency=statement.currency)),
                ],
            )
            operations.append(AddTransaction(transaction=transaction))
        if assert_balance:
            if statement.closing_balance is None or statement.end is None:
                raise RecipeError("this statement has no closing balance to assert")
            operations.append(Reconcile(
                account=item.account, date=statement.end + dt.timedelta(days=1),
                amount=Amount(number=statement.closing_balance, currency=statement.currency),
            ))
        if version is None:
            version = (await self._ledgers.get_ledger(ledger_id)).version
        summary = note or f"Import {item.filename}: {len(chosen)} of {len(statement.lines)} lines"
        change = await self._changes.submit(ledger_id, SubmitChangeRequest(operation=Batch(operations=operations), note=summary), caller, version)
        item.change_ids.append(change.id)
        await asyncio.to_thread(items.save, item)
        return change
