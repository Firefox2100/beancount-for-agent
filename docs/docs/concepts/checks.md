---
title: Checks
---

`get_checks` (REST: `GET /ledgers/{id}/checks?stale_days=`) lists things in the books that deserve a look. It is read-only and conservative: each finding says what was seen and leaves the decision to a person, or to an agent that then makes the usual proposals.

| Kind | Severity | What it means |
| --- | --- | --- |
| `ledger_error` | warning | The ledger has a parse, booking or balance error. |
| `overdrawn` | warning | A cash, savings or wallet account is below zero, which usually means a missing income or transfer. |
| `duplicate` | warning | Entries with the same date, text, accounts and amounts. Recurring entries are skipped. |
| `stale_balance` | info | An account with a balance has not been checked against the bank for more than `stale_days` days (45 by default), or never. |
| `uncategorised` | info | Entries in an account whose name contains *uncategorised*, *unknown* or *unsorted*. |
| `pending` | info | Entries flagged `!`, not yet confirmed. |
| `future` | info | Entries dated after today. |
| `unused` | info | An empty account nothing has been booked to for 180 days, which could be closed. |

The overview in the web interface lists the first findings under **Worth a look**.
