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

## Financial position

`get_financial_position` (REST: `GET /ledgers/{id}/financial-position?interval=&points=&today=`) answers "how am I doing over time". It gives assets, liabilities and the net position at up to twelve weekly or monthly points, plus an allocation of the assets by account. Every figure is in the original currencies, exactly as recorded.

### Reference values

If the ledger has an operating currency, each total can also carry an **approximate reference value** in that currency, converted at a rate the service fetched. These values are for reading only: they never drive a ledger entry, they are marked `approximate`, and a currency without a rate is reported as missing instead of being guessed.

Reference rates are **off by default**. With `BEANCOUNT_MCP_REFERENCE_RATES_ENABLED=true` the service asks [Frankfurter](https://frankfurter.dev) (or a self-hosted instance set by `BEANCOUNT_MCP_REFERENCE_RATES_URL`) for rates, and caches them on disk. A request carries only currency codes and dates, never an amount or an account. A cached rate is fresh for 24 hours by default, then served stale for a further 12 while it refreshes in the background. A day the provider has no rate for keeps the last known one and says so. The user can clear the cache with `POST /ledgers/{id}/reference-rates/refresh`; `GET .../reference-rates/status` reports its state.

## Scheduling is not the service's job

The service never schedules anything. A harness polls these views, for example at the start of a session, and proposes the resulting actions for you to approve.
