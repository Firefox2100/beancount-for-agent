import datetime as dt
import uuid
from decimal import Decimal
from pathlib import Path

from beancount.core import data
from beancount.core.amount import Amount as BcAmount
from beancount.parser import printer

from beancount_mcp.ledger.errors import NotEditable, TransactionNotFound
from beancount_mcp.ledger.layout import accounts_file, transaction_file
from beancount_mcp.ledger.read import find_record, find_transaction
from beancount_mcp.models.details import meta_key, to_meta
from beancount_mcp.models import (
    AddDirective,
    AddTransaction,
    Batch,
    BalanceAssertion,
    CloseAccount,
    CommodityDirective,
    DeleteDirective,
    DeleteTransaction,
    Directive,
    EventDirective,
    Layout,
    NoteDirective,
    OpenAccount,
    Operation,
    PadDirective,
    PriceDirective,
    Reconcile,
    SetAccountDetails,
    TransactionInput,
    UpdateDirective,
    UpdateTransaction,
)


def apply_operation(stage: Path, layout: Layout, entries: list, operation: Operation) -> dict:
    """Edit the staged ledger files in place and return what the change touched."""
    match operation:
        case AddTransaction():
            new_id = uuid.uuid4().hex
            _append(stage / transaction_file(layout, operation.transaction.date),
                    _render_transaction(operation.transaction, new_id))
            return {"transaction_id": new_id}
        case UpdateTransaction():
            return _update_transaction(stage, layout, entries, operation)
        case DeleteTransaction():
            entry = _editable_transaction(stage, entries, operation.id)
            _remove_span(Path(entry.meta["filename"]), entry.meta["lineno"])
            return {}
        case OpenAccount():
            _append(stage / accounts_file(layout), _render_open(operation))
            return {"account": operation.account}
        case SetAccountDetails():
            return _set_details(stage, entries, operation)
        case CloseAccount():
            _append(stage / accounts_file(layout), _render_close(operation))
            return {"account": operation.account}
        case AddDirective():
            new_id = uuid.uuid4().hex
            _append(stage / _directive_file(layout, operation.directive), _render_directive(operation.directive, new_id))
            return {"record_id": new_id}
        case UpdateDirective():
            return _update_directive(stage, layout, entries, operation)
        case Reconcile():
            return _reconcile(stage, layout, operation)
        case Batch():
            touched: dict = {}
            for member in operation.operations:
                for key, value in apply_operation(stage, layout, entries, member).items():
                    touched.setdefault(key, value)
            return touched
        case DeleteDirective():
            entry = _editable_record(stage, entries, operation.id)
            _remove_span(Path(entry.meta["filename"]), entry.meta["lineno"])
            return {}


def _set_details(stage: Path, entries: list, operation: SetAccountDetails) -> dict:
    entry = next((e for e in entries if isinstance(e, data.Open) and e.account == operation.account), None)
    if entry is None:
        raise TransactionNotFound(operation.account)
    _require_in_stage(stage, entry, operation.account)
    cleared = {meta_key(name) for name in operation.clear}
    meta = {k: v for k, v in entry.meta.items() if k not in ("filename", "lineno") and k not in cleared}
    meta.update(to_meta(operation.set))
    text = printer.format_entry(data.Open(meta, entry.date, entry.account, entry.currencies, entry.booking))
    _replace_span(Path(entry.meta["filename"]), entry.meta["lineno"], text)
    return {"account": operation.account}


def _update_transaction(stage: Path, layout: Layout, entries: list, operation: UpdateTransaction) -> dict:
    entry = _editable_transaction(stage, entries, operation.id)
    stored_id = entry.meta.get("id") or uuid.uuid4().hex
    text = _render_transaction(operation.transaction, str(stored_id))
    current = Path(entry.meta["filename"])
    target = stage / transaction_file(layout, operation.transaction.date)
    if current.resolve() == target.resolve():
        _replace_span(current, entry.meta["lineno"], text)
    else:
        _remove_span(current, entry.meta["lineno"])
        _append(target, text)
    return {"transaction_id": str(stored_id)}


def _reconcile(stage: Path, layout: Layout, operation: Reconcile) -> dict:
    balance = BalanceAssertion(date=operation.date, account=operation.account, amount=operation.amount)
    balance_id = uuid.uuid4().hex
    if operation.pad_account:
        pad = PadDirective(
            date=operation.date - dt.timedelta(days=1),
            account=operation.account,
            source_account=operation.pad_account,
        )
        _append(stage / _directive_file(layout, pad), _render_directive(pad, uuid.uuid4().hex))
    _append(stage / _directive_file(layout, balance), _render_directive(balance, balance_id))
    return {"record_id": balance_id}


def _update_directive(stage: Path, layout: Layout, entries: list, operation: UpdateDirective) -> dict:
    entry = _editable_record(stage, entries, operation.id)
    stored_id = str(entry.meta.get("id") or uuid.uuid4().hex)
    text = _render_directive(operation.directive, stored_id)
    current = Path(entry.meta["filename"])
    target = stage / _directive_file(layout, operation.directive)
    if current.resolve() == target.resolve():
        _replace_span(current, entry.meta["lineno"], text)
    else:
        _remove_span(current, entry.meta["lineno"])
        _append(target, text)
    return {"record_id": stored_id}


def _directive_file(layout: Layout, directive: Directive) -> str:
    if isinstance(directive, CommodityDirective):
        return accounts_file(layout)
    return transaction_file(layout, directive.date)


def _render_directive(directive: Directive, identifier: str) -> str:
    meta = {"id": identifier}
    match directive:
        case BalanceAssertion():
            entry = data.Balance(meta, directive.date, directive.account, _amount(directive.amount),
                                 directive.tolerance, None)
        case PadDirective():
            entry = data.Pad(meta, directive.date, directive.account, directive.source_account)
        case PriceDirective():
            entry = data.Price(meta, directive.date, directive.currency, _amount(directive.amount))
        case CommodityDirective():
            entry = data.Commodity(meta, directive.date, directive.currency)
        case NoteDirective():
            entry = data.Note(meta, directive.date, directive.account, directive.comment, None, None)
        case EventDirective():
            entry = data.Event(meta, directive.date, directive.type, directive.description)
    return printer.format_entry(entry)


def _editable_record(stage: Path, entries: list, identifier: str):
    entry = find_record(entries, identifier)
    if entry is None:
        raise TransactionNotFound(identifier)
    _require_in_stage(stage, entry, identifier)
    return entry


def _require_in_stage(stage: Path, entry, identifier: str) -> None:
    filename = entry.meta.get("filename", "")
    if not Path(filename).resolve().is_relative_to(stage.resolve()):
        raise NotEditable(f"{identifier} was not written in a ledger file")


def _editable_transaction(stage: Path, entries: list, identifier: str) -> data.Transaction:
    entry = find_transaction(entries, identifier)
    if entry is None:
        raise TransactionNotFound(identifier)
    _require_in_stage(stage, entry, identifier)
    return entry


def _render_transaction(transaction: TransactionInput, identifier: str) -> str:
    priced = any(posting.price is not None for posting in transaction.postings)
    postings = [
        data.Posting(
            account=posting.account,
            units=_amount(posting.units, with_cents=priced),
            cost=_cost(posting.cost),
            price=_amount(posting.price),
            flag=None,
            meta=None,
        )
        for posting in transaction.postings
    ]
    entry = data.Transaction(
        meta={"id": identifier, **transaction.meta},
        date=transaction.date,
        flag=transaction.flag,
        payee=transaction.payee,
        narration=transaction.narration,
        tags=frozenset(transaction.tags),
        links=frozenset(transaction.links),
        postings=postings,
    )
    return printer.format_entry(entry)


def _amount(amount, with_cents: bool = False) -> BcAmount | None:
    """Convert to a Beancount amount.

    Beancount infers balancing tolerance from decimal places, and whole numbers
    give none. A priced posting divides to a repeating unit price, so its
    transaction must show decimals or the rounding residue is reported as an error.
    """
    if amount is None:
        return None
    number = Decimal(amount.number)
    if with_cents and number.as_tuple().exponent >= 0:
        number = number.quantize(Decimal("0.01"))
    return BcAmount(number, amount.currency)


def _cost(cost) -> data.CostSpec | None:
    if cost is None:
        return None
    return data.CostSpec(cost.number, None, cost.currency, cost.date, cost.label, False)


def _render_open(operation: OpenAccount) -> str:
    booking = data.Booking[operation.booking] if operation.booking else None
    meta = {"type": operation.type} if operation.type else {}
    if operation.details is not None:
        meta.update(to_meta(operation.details))
    return printer.format_entry(
        data.Open(meta, operation.date, operation.account, list(operation.currencies) or None, booking)
    )


def _render_close(operation: CloseAccount) -> str:
    return printer.format_entry(data.Close({}, operation.date, operation.account))


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text() if path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    separator = "\n" if existing.strip() and text.count("\n") > 1 else ""
    path.write_text(existing + separator + text)


def _span(lines: list[str], lineno: int) -> tuple[int, int]:
    start = lineno - 1
    end = start + 1
    while end < len(lines) and lines[end][:1] in (" ", "\t"):
        end += 1
    if end < len(lines) and not lines[end].strip():
        end += 1
    return start, end


def _remove_span(path: Path, lineno: int) -> None:
    lines = path.read_text().splitlines(keepends=True)
    start, end = _span(lines, lineno)
    path.write_text("".join(lines[:start] + lines[end:]))


def _replace_span(path: Path, lineno: int, text: str) -> None:
    lines = path.read_text().splitlines(keepends=True)
    start, end = _span(lines, lineno)
    rest = lines[end:]
    separator = "\n" if rest else ""
    path.write_text("".join(lines[:start]) + text + separator + "".join(rest))
