import datetime as dt
import os
import re
import uuid
from decimal import Decimal
from pathlib import Path

from beancount.core import data
from beancount.core.amount import Amount as BcAmount
from beancount.parser import printer
from beancount.parser.grammar import ValueType

from beancount_mcp.ledger.errors import NotEditable, TransactionNotFound
from beancount_mcp.ledger.layout import MAIN_FILE, accounts_file, transaction_file
from beancount_mcp.ledger.read import find_record, find_transaction, to_transaction
from beancount_mcp.models.details import meta_key, to_meta
from beancount_mcp.models import (
    AddDirective,
    AttachReceipt,
    CustomDirective,
    DocumentDirective,
    QueryDirective,
    SetOption,
    SetProfileItem,
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
            target = stage / _directive_file(layout, operation.directive)
            _append(target, _render_directive(operation.directive, new_id, stage, target))
            return {"record_id": new_id}
        case AttachReceipt():
            return _attach_receipt(stage, layout, entries, operation)
        case SetOption():
            return _set_option(stage, operation)
        case SetProfileItem():
            raise NotEditable("profile items are changed through the profile, not the ledger files")
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
    current = Path(entry.meta["filename"])
    target = stage / _directive_file(layout, operation.directive)
    text = _render_directive(operation.directive, stored_id, stage, target)
    if current.resolve() == target.resolve():
        _replace_span(current, entry.meta["lineno"], text)
    else:
        _remove_span(current, entry.meta["lineno"])
        _append(target, text)
    return {"record_id": stored_id}


def _attach_receipt(stage: Path, layout: Layout, entries: list, operation: AttachReceipt) -> dict:
    """Link a stored receipt to a transaction, the way Fava expects: a document entry and a `document` note."""
    entry = _editable_transaction(stage, entries, operation.id)
    current = to_transaction(entry)
    name = operation.path.rsplit("/", 1)[-1]
    meta = dict(current.meta)
    if name not in meta.values():
        key = "document" if "document" not in meta else next(f"document-{n}" for n in range(2, 100) if f"document-{n}" not in meta)
        meta[key] = name
    update = UpdateTransaction(id=operation.id, transaction=TransactionInput(**{**current.model_dump(exclude={"id"}), "meta": meta}))
    _update_transaction(stage, layout, entries, update)
    account = next((p.account for p in current.postings if p.account.split(":")[0] in ("Assets", "Liabilities")), current.postings[0].account)
    directive = DocumentDirective(date=current.date, account=account, path=operation.path)
    target = stage / _directive_file(layout, directive)
    _append(target, _render_directive(directive, uuid.uuid4().hex, stage, target))
    return {"transaction_id": operation.id}


def _directive_file(layout: Layout, directive: Directive) -> str:
    if isinstance(directive, CommodityDirective):
        return accounts_file(layout)
    return transaction_file(layout, directive.date)


def _render_directive(directive: Directive, identifier: str, stage: Path | None = None, target: Path | None = None) -> str:
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
        case DocumentDirective():
            # Beancount reads a document's path relative to the file it is written in.
            filename = os.path.relpath(stage / directive.path, target.parent)  # type: ignore[operator]
            entry = data.Document(meta, directive.date, directive.account, filename, None, None)
        case QueryDirective():
            entry = data.Query(meta, directive.date, directive.name, directive.query)
        case CustomDirective():
            entry = data.Custom(meta, directive.date, directive.type, [_custom_item(v) for v in directive.values])
        case EventDirective():
            entry = data.Event(meta, directive.date, directive.type, directive.description)
    return printer.format_entry(entry)


def _custom_item(value) -> ValueType:
    from beancount.core import account as bc_account

    match value.type:
        case "account":
            return ValueType(value.value, bc_account.TYPE)
        case "amount":
            return ValueType(_amount(value.value), BcAmount)
        case "bool":
            return ValueType(value.value, bool)
        case "date":
            return ValueType(value.value, dt.date)
        case "number":
            return ValueType(value.value, Decimal)
    return ValueType(value.value, str)


_OPTION_LINE = re.compile(r'^option\s+"([^"]+)"\s+"([^"]*)"\s*$')


def _set_option(stage: Path, operation: SetOption) -> dict:
    """Edit the option lines of the entry-point file, leaving every other line as it is."""
    main = stage / MAIN_FILE
    lines = main.read_text().split("\n")
    found = [(i, m.group(2)) for i, line in enumerate(lines) if (m := _OPTION_LINE.match(line)) and m.group(1) == operation.name]
    new_line = f'option "{operation.name}" "{operation.value}"'
    if operation.name == "operating_currency":
        matching = [i for i, value in found if value == operation.value]
        if operation.remove:
            if not matching:
                raise TransactionNotFound(f"operating currency {operation.value} is not set")
            lines = [line for i, line in enumerate(lines) if i not in matching]
        elif not matching:
            lines.insert(_after_options(lines), new_line)
    elif operation.remove:
        if not found:
            raise TransactionNotFound(f"option {operation.name} is not set")
        lines = [line for i, line in enumerate(lines) if i not in {i for i, _ in found}]
    elif found:
        first = found[0][0]
        lines = [new_line if i == first else line for i, line in enumerate(lines) if i == first or i not in {j for j, _ in found}]
    else:
        lines.insert(_after_options(lines), new_line)
    main.write_text("\n".join(lines))
    return {}


def _after_options(lines: list[str]) -> int:
    last = max((i for i, line in enumerate(lines) if _OPTION_LINE.match(line)), default=-1)
    return last + 1


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
