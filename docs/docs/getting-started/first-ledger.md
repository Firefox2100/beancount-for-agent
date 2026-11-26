---
title: Create your first ledger
---

You can do this three ways. They all end in the same place: a folder under the data folder with a `main.beancount` in it.

## Through your agent

Once an agent is connected ([Claude Code](../guides/claude-code.md), [DeepSeek Harness](../guides/deepseek-harness.md), [other MCP clients](../guides/other-agents.md)), ask it:

> Create a ledger called `personal`. My main currency is GBP, and I also use CNY and USD.

It calls `create_ledger`. Creating a ledger is the one direct write an agent can make, because an empty ledger holds nothing worth approving.

## Through the API

```bash
curl -s -X POST localhost:8421/ledgers \
  -H "authorization: Bearer <token>" -H "content-type: application/json" \
  -d '{"id": "personal", "operating_currencies": ["GBP", "CNY", "USD"]}'
```

The ledger id must match `^[a-z0-9][a-z0-9_-]{0,63}$`, because it becomes a folder name.

## By copying a folder

The file system is the source of truth. Copy an existing ledger folder into the data folder and it is listed on the next request. A folder without a sidecar is adopted if its files match one of the three layouts exactly. Anything else is refused rather than converted. See [Ledgers](../concepts/ledgers.md).

## Add accounts and an opening balance

A ledger needs accounts before it can hold anything. Opening an account, and every other change an agent makes, is a [proposal](../concepts/proposals.md) you approve. A good first conversation:

1. Ask the agent to open an account, for example *"Open a checking account called Assets:Barclays:Current in GBP"*, and `Equity:Opening-Balances`.
2. Approve both in the web interface at `/ui/`.
3. Ask for the opening balance: *"Record an opening balance of 48,469.17 GBP in Barclays Current."* The agent books it against `Equity:Opening-Balances`. Approve it.
4. Ask for the balances to check them.

:::note Why Equity goes negative
Every entry sums to zero. The opening balance moves money out of `Equity:Opening-Balances` (shown as a negative number) into your account. That is not a debt: it is how the books say "this came from before I started tracking". See [Worked examples](../guides/worked-examples.md).
:::

## Dates and opening dates

An account must be open before anything can use it, and an entry dated before its account opened is refused. When you set up accounts for money you already have, open them from the date of your oldest entry. An account's open date cannot be changed through the tools; it can be edited in [Fava](../guides/fava.md).
