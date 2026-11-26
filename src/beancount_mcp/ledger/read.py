import hashlib
from collections import defaultdict
from datetime import date
from decimal import Decimal

from beancount.core import data
from beancount.core.inventory import Inventory
from beancount.parser import printer

from beancount_mcp.models import (
    AccountBalance,
    AccountInfo,
    BalanceAssertion,
    CommodityDirective,
    Directive,
    EventDirective,
    NoteDirective,
    PadDirective,
    PriceDirective,
    Record,
    Transaction,
)
from beancount_mcp.models.common import Amount
from beancount_mcp.models.details import from_meta
from beancount_mcp.models.transactions import Cost, Posting

HIDDEN_META = {"filename", "lineno", "id"}
USER_FLAGS = {"*", "!"}


def is_user_transaction(entry) -> bool:
    return isinstance(entry, data.Transaction) and entry.flag in USER_FLAGS


RECORD_TYPES = (data.Balance, data.Pad, data.Price, data.Commodity, data.Note, data.Event)


def entry_fingerprint(entry) -> str:
    return hashlib.sha1(printer.format_entry(entry).encode()).hexdigest()


def transaction_id(entry) -> str:
    """The stored id, or a content hash for entries we did not write."""
    stored = entry.meta.get("id")
    if stored:
        return str(stored)
    return "h" + entry_fingerprint(entry)[:16]


def is_record(entry) -> bool:
    return isinstance(entry, RECORD_TYPES)


def find_record(entries: list, identifier: str):
    for entry in entries:
        if is_record(entry) and transaction_id(entry) == identifier:
            return entry
    return None


def to_directive(entry) -> Directive:
    match entry:
        case data.Balance():
            return BalanceAssertion(
                date=entry.date,
                account=entry.account,
                amount=_to_amount(entry.amount),
                tolerance=entry.tolerance,
            )
        case data.Pad():
            return PadDirective(date=entry.date, account=entry.account, source_account=entry.source_account)
        case data.Price():
            return PriceDirective(date=entry.date, currency=entry.currency, amount=_to_amount(entry.amount))
        case data.Commodity():
            return CommodityDirective(date=entry.date, currency=entry.currency)
        case data.Note():
            return NoteDirective(date=entry.date, account=entry.account, comment=entry.comment)
        case data.Event():
            return EventDirective(date=entry.date, type=entry.type, description=entry.description)
    raise TypeError(type(entry).__name__)


def to_record(entry) -> Record:
    return Record(id=transaction_id(entry), directive=to_directive(entry))


def list_records(
    entries: list,
    *,
    kind: str | None = None,
    account: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> list[Record]:
    result = []
    for entry in entries:
        if not is_record(entry):
            continue
        record = to_record(entry)
        if kind and record.directive.kind != kind:
            continue
        if start and entry.date < start or end and entry.date > end:
            continue
        if account and not _in_account(getattr(entry, "account", ""), account):
            continue
        result.append(record)
    return result


def to_transaction(entry: data.Transaction) -> Transaction:
    return Transaction(
        id=transaction_id(entry),
        date=entry.date,
        flag=entry.flag,
        payee=entry.payee,
        narration=entry.narration or "",
        tags=sorted(entry.tags or ()),
        links=sorted(entry.links or ()),
        postings=[_to_posting(posting) for posting in entry.postings],
        meta={
            key: str(value)
            for key, value in entry.meta.items()
            if key not in HIDDEN_META and not key.startswith("__")
        },
    )


def _to_posting(posting: data.Posting) -> Posting:
    cost = None
    if posting.cost is not None:
        cost = Cost(
            number=posting.cost.number,
            currency=posting.cost.currency,
            date=posting.cost.date,
            label=posting.cost.label,
        )
    return Posting(
        account=posting.account,
        units=_to_amount(posting.units),
        cost=cost,
        price=_to_amount(posting.price),
    )


def _to_amount(amount) -> Amount | None:
    if amount is None or amount.number is None:
        return None
    return Amount(number=amount.number, currency=amount.currency)


def find_transaction(entries: list, transaction_id_: str) -> data.Transaction | None:
    for entry in entries:
        if is_user_transaction(entry) and transaction_id(entry) == transaction_id_:
            return entry
    return None


def list_transactions(
    entries: list,
    *,
    account: str | None = None,
    start: date | None = None,
    end: date | None = None,
    text: str | None = None,
    tag: str | None = None,
) -> list[Transaction]:
    needle = text.lower() if text else None
    result = []
    for entry in entries:
        if not is_user_transaction(entry):
            continue
        if start and entry.date < start or end and entry.date > end:
            continue
        if tag and tag not in (entry.tags or ()):
            continue
        if account and not any(_in_account(p.account, account) for p in entry.postings):
            continue
        if needle and needle not in f"{entry.payee or ''}\n{entry.narration or ''}".lower():
            continue
        result.append(to_transaction(entry))
    return result


def _in_account(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ":")


def list_accounts(entries: list) -> list[AccountInfo]:
    accounts: dict[str, AccountInfo] = {}
    for entry in entries:
        if isinstance(entry, data.Open):
            accounts[entry.account] = AccountInfo(
                name=entry.account,
                open_date=entry.date,
                currencies=list(entry.currencies or []),
                booking=entry.booking.name if entry.booking else None,
                type=entry.meta.get("type"),
                details=from_meta(entry.meta),
            )
        elif isinstance(entry, data.Close) and entry.account in accounts:
            accounts[entry.account].close_date = entry.date
    return sorted(accounts.values(), key=lambda info: info.name)


def balances(entries: list, as_of: date | None = None) -> list[AccountBalance]:
    inventories: dict[str, Inventory] = defaultdict(Inventory)
    for entry in entries:
        if not isinstance(entry, data.Transaction) or (as_of and entry.date > as_of):
            continue
        for posting in entry.postings:
            if posting.units is not None and posting.units.number is not None:
                inventories[posting.account].add_amount(posting.units)

    result = []
    for account in sorted(inventories):
        amounts: dict[str, Decimal] = {
            position.units.currency: position.units.number
            for position in inventories[account]
        }
        result.append(
            AccountBalance(
                account=account,
                balances={currency: format(number, "f") for currency, number in sorted(amounts.items())},
            )
        )
    return result
