---
title: Views
---

Views are read-only summaries that answer *what is open, due or available* without an agent adding up postings itself. They are computed by the service (`ledger/views.py`), and available both to agents and through the API.

## Open items

`get_open_items` (REST: `GET /ledgers/{id}/open-items?account=`) lists what is still unsettled on receivable and payable accounts: items grouped by link, with what remains per currency, plus the net of postings that carry no link, such as a payment that was not matched. Positive on a receivable, negative on a payable.

## Due

`get_due` (REST: `GET /ledgers/{id}/due?within_days=&today=`) covers accounts under `Liabilities:` whose profile has a `statement_day` or `due_day`. For each it gives:

- what is owed, including unbilled amounts, per currency,
- the next statement date and the due date, and the days until it is due,
- the autopay source, if one is set.

With `within_days`, only accounts with a balance due in that window are returned. Short months are handled: a due day of 31 falls on the last day of a month that has fewer.

## Credit pools

`get_credit_pools` (REST: `GET /ledgers/{id}/pools?today=`) shows each pool's limit, what is used and what is available. Several cards can share one allowance: a pool in the profile has a limit, and the used amount is the members' liabilities, including sub-accounts such as `Unbilled`, converted with the ledger's `price` directives.

Amounts in a currency with no price to the limit currency are listed as `unconverted` and not counted.

:::caution A pool has one limit
A pool has a single limit in a single currency. Banks that give a card two separate limits (one per currency) with their own provisional conversion cannot be tracked exactly, and the bank's own figure is the one to trust. Many people simply do not use pools for such a card.
:::

## Scheduling is not the service's job

The service never schedules anything. A harness polls these views, for example at the start of a session, and proposes the resulting actions for you to approve.
