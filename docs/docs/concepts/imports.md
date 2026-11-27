---
title: Importing statements
---

Typing every transaction does not scale. Importing turns a statement file from the bank into one proposal, which you approve like any other change.

## The flow

1. **You upload** the statement in the web interface (**Statements**, per ledger), choosing the account it belongs to. Only a person can upload or delete one, because a file is the one input that has not passed through the approval gate. Only the parsed statement is kept, never the original file.
2. **The agent reads it.** `list_imports` and `get_import` show the numbered lines. Each is marked **new**, **imported** (the ledger already holds that bank id) or **possible duplicate** (a transaction on the account with the same amount within two days, entered by hand).
3. **The agent proposes.** `propose_import` takes an account for every line (`categories`, with `default_account` for the rest) and makes one batch proposal for the lines that are new. `skip` leaves lines out, `include` adds a possible duplicate anyway, and `assert_balance` also asserts the statement's closing balance the day after it ends.
4. **You approve** the batch in the inbox, with every posting shown. Each imported transaction carries the bank's id as `bank-ref` metadata, so uploading the same file again finds everything already there.

The service checks the file against the account when it is uploaded and warns when the currency does not match, when the file names a different account number or IBAN than the one recorded, or when the opening balance plus the lines does not reach the closing balance.

## Formats

| Format | Id | Notes |
| --- | --- | --- |
| OFX and QFX | `ofx` | Bank and credit-card statements, both the older SGML form and XML. Investment statements are not supported. |
| ISO 20022 camt.053 | `camt053` | Booked entries only. camt.052 reports read the same way. Files declaring a DTD are refused. |
| SWIFT MT940 | `mt940` | The value date is the line's date. |

Amounts are signed from the account holder's side: money in is positive, money out negative. A file with several statements becomes several imports.

CSV has no standard, so there is no built-in CSV reader. A bank that offers none of the formats above needs an importer written for it.

## Writing an importer

An importer is a small Python class, installed by whoever runs the service and never by an agent. It only reads bytes and returns statements; it never sees the ledger, so what it produces is reviewed and approved like everything else.

```python
import datetime as dt
from decimal import Decimal

from beancount_mcp.imports.base import ImportFailed, Importer
from beancount_mcp.models.imports import Statement, StatementLine


class AcmeCsv(Importer):
    id = "acme-csv"
    title = "Acme Bank CSV"

    def identify(self, filename: str, data: bytes) -> bool:
        return data.startswith(b"Date,Description,Amount")

    def parse(self, data: bytes) -> list[Statement]:
        lines = []
        for row in data.decode().splitlines()[1:]:
            day, description, amount = row.split(",")
            lines.append(StatementLine(date=dt.date.fromisoformat(day), description=description, amount=Decimal(amount)))
        if not lines:
            raise ImportFailed("the file has no transactions")
        return [Statement(format=self.id, currency="GBP", lines=lines)]


def register(registry):
    registry.register(AcmeCsv())
```

Expose `register` as an entry point in the `beancount_mcp.importers` group in the package's `pyproject.toml`:

```toml
[project.entry-points."beancount_mcp.importers"]
acme = "acme_importer:register"
```

`identify` must be cheap and must not raise. `parse` raises `ImportFailed` with a reason a person can act on. Give each line a `reference` when the bank has an id for it, because that is what makes re-uploading safe. A statement may also carry opening and closing balances, which enable the balance check.

A plugin's `identify` and `parse` errors are reported to the person uploading and never stop the service. A registry for sharing importers may come later.
