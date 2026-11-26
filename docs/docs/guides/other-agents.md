---
title: Other agents (MCP)
---

Any agent that speaks the Model Context Protocol over HTTP can use the service. MCP is the universal surface: it is stateless, has a curated set of [tools](../reference/mcp-tools.md), and works with no plugin.

## Connect

Run the service with `BEANCOUNT_MCP_MCP_ENABLED=true`. The endpoint is streamable HTTP at:

```text
http://<host>:<port>/mcp
```

Send the bearer token as `Authorization: Bearer <token>`. Most clients take this as a header in the server entry. For example, in a client that reads an `.mcp.json`-style file:

```json
{
  "mcpServers": {
    "beancount": {
      "type": "http",
      "url": "http://127.0.0.1:8421/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

The server's own instructions tell the model to start with `list_accounts`, to prefer `record_expense`, `record_income` and `record_transfer` for everyday events, to use `list_recipes` and `perform_recipe` for anything account-specific, and that every change waits for approval.

## What the model can do

- **Read:** `list_ledgers`, `list_accounts`, `list_account_types`, `get_balances`, `search_transactions`, `get_open_items`, `get_due`, `get_credit_pools`, `list_recipes`.
- **Propose:** `record_expense`, `record_income`, `record_transfer`, `reconcile_account`, `open_account`, `close_account`, `perform_recipe`, `amend_transaction`, `delete_transaction`.
- **Own proposals:** `list_my_proposals`, `withdraw_proposal`. There is no approve tool.
- **Direct:** `create_ledger`.

Every tool carries annotations (`readOnlyHint`, `destructiveHint`) and a tag (`read`, `propose`, `recipe`, `admin`), so a client can mask or gate groups of them. `ledger` has the same name and is optional on every tool that takes it, so a client or proxy can inject or mask it mechanically.

## Approving

An MCP client cannot approve. Use the [web interface](web-interface.md), or call the REST API yourself. If your harness supports plugins, a plugin can do it inside the harness, as the [Claude Code](claude-code.md) and [DeepSeek Harness](deepseek-harness.md) integrations do.

## Give the model the guide

The plugins ship a skill that explains how the books are modelled: double entry, account types, currencies, open items, balance checks. A client without plugins can paste the text of `integrations/claude-code/skills/beancount/SKILL.md` into its instructions. Models that already know Beancount need it less; local and smaller models benefit most.

## Keep the token out of the agent's reach

Give the token to the MCP connection and nowhere else. If the harness also gives the model a shell or file tools, make sure it cannot read the environment, the config file that holds the token, or the data folder. See [Security](../concepts/security.md).
