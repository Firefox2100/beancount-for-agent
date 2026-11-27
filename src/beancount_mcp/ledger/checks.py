"""Things in the books that deserve a look: errors, stale balances, likely duplicates and the like.

Read-only and deliberately conservative. Each finding says what was seen, so a person or an agent can decide.
"""

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from beancount.core import data

from beancount_mcp.ledger.read import transaction_id as entry_id
from beancount_mcp.models import AccountInfo
from beancount_mcp.models.checks import Finding

CREDIT_TYPES = {"credit_card", "loan", "payable"}
RECONCILED_TYPES = {"checking", "savings", "credit_card", "ewallet"}
UNUSED_DAYS = 180
UNCATEGORISED = ("uncategor", "unknown", "unsorted")
MAX_LISTED = 10


def _list(items: list[str]) -> str:
    shown = ", ".join(items[:MAX_LISTED])
    return shown + (f" and {len(items) - MAX_LISTED} more" if len(items) > MAX_LISTED else "")


def checks(entries: list, accounts: list[AccountInfo], balances: dict[str, dict[str, Decimal]], errors: list, today: dt.date, stale_days: int) -> list[Finding]:
    found: list[Finding] = []
    for error in errors[:MAX_LISTED]:
        found.append(Finding(kind="ledger_error", severity="warning", title="The ledger has an error", detail=error.message))

    transactions = [e for e in entries if isinstance(e, data.Transaction)]
    last_balance: dict[str, dt.date] = {}
    for entry in entries:
        if isinstance(entry, data.Balance):
            last_balance[entry.account] = max(entry.date, last_balance.get(entry.account, entry.date))
    last_used: dict[str, dt.date] = {}
    for transaction in transactions:
        for posting in transaction.postings:
            last_used[posting.account] = max(transaction.date, last_used.get(posting.account, transaction.date))

    for info in accounts:
        if info.close_date is not None:
            continue
        held = balances.get(info.name, {})
        nonzero = {c: n for c, n in held.items() if n != 0}
        if info.name.startswith("Assets:") and info.type not in CREDIT_TYPES:
            negative = {c: n for c, n in nonzero.items() if n < 0}
            if negative:
                shown = ", ".join(f"{format(n, ',f')} {c}" for c, n in sorted(negative.items()))
                found.append(Finding(kind="overdrawn", severity="warning", title=f"{info.name} is below zero", detail=f"It holds {shown}. Money may be missing from an income or transfer entry.", account=info.name))
        if info.type in RECONCILED_TYPES and nonzero:
            seen = last_balance.get(info.name)
            if seen is None or (today - seen).days > stale_days:
                since = "never" if seen is None else f"since {seen}"
                found.append(Finding(kind="stale_balance", severity="info", title=f"{info.name} has not been checked against the bank {since}", detail="Compare it with the bank's balance and reconcile, so a missing entry shows up.", account=info.name))
        used = last_used.get(info.name, info.open_date)
        if not nonzero and (today - used).days > UNUSED_DAYS and info.type != "brokerage":
            found.append(Finding(kind="unused", severity="info", title=f"{info.name} looks unused", detail=f"It is empty and nothing was booked to it since {used}. It could be closed.", account=info.name))

    uncategorised: dict[str, list[str]] = defaultdict(list)
    pending: list[str] = []
    future: list[str] = []
    for transaction in transactions:
        ident = entry_id(transaction)
        if transaction.flag == "!":
            pending.append(ident)
        if transaction.date > today:
            future.append(ident)
        for posting in transaction.postings:
            if any(word in posting.account.lower() for word in UNCATEGORISED):
                uncategorised[posting.account].append(ident)
    for account, ids in sorted(uncategorised.items()):
        found.append(Finding(kind="uncategorised", severity="info", title=f"{len(ids)} transaction(s) in {account}", detail="They still need a proper account.", account=account, transactions=ids[:MAX_LISTED]))
    if pending:
        found.append(Finding(kind="pending", severity="info", title=f"{len(pending)} transaction(s) are flagged as pending", detail="They carry the ! flag and have not been confirmed.", transactions=pending[:MAX_LISTED]))
    if future:
        found.append(Finding(kind="future", severity="info", title=f"{len(future)} transaction(s) are dated in the future", detail="Check the date, or ignore it if they are planned.", transactions=future[:MAX_LISTED]))

    groups: dict[tuple, list[str]] = defaultdict(list)
    for transaction in transactions:
        if transaction.meta.get("recurring") or len(transaction.postings) < 2:
            continue
        key = (transaction.date, (transaction.payee or "").lower(), transaction.narration.lower(),
               tuple(sorted((p.account, p.units.currency, str(p.units.number)) for p in transaction.postings if p.units and p.units.number is not None)))
        groups[key].append(entry_id(transaction))
    for key, ids in sorted(groups.items(), key=lambda item: item[0][0]):
        if len(ids) > 1:
            label = key[1] or key[2] or "a transaction"
            found.append(Finding(kind="duplicate", severity="warning", title=f"{len(ids)} identical entries on {key[0]}: {label}", detail=f"Same date, text, accounts and amounts ({_list(ids)}). If it was recorded twice, delete one.", transactions=ids[:MAX_LISTED]))
    order = {"warning": 0, "info": 1}
    return sorted(found, key=lambda f: (order[f.severity], f.kind, f.title))
