---
slug: /introduction
title: Beancount for agents
sidebar_label: Introduction
---

Beancount for agents is a service that lets AI agents record and look up your finances in a [Beancount](https://beancount.github.io/) ledger. The ledger stays a plain text file you own. The agent never touches that text: it works through a small set of operations, and this service owns the file.

## The idea

Agents are useful for bookkeeping. They can read a receipt, understand "I paid the pharmacy 18.65 pounds on my card", and know which accounts that touches. They are also unreliable with exact syntax, arithmetic and foreign exchange, and you do not want one rewriting your books unreviewed. So the service puts three things between the agent and the ledger:

- The agent asks to *record an expense*, *pay the card bill* or *reconcile this account*. The service turns that intent into the right postings, in several currencies if needed, and does the arithmetic.
- Every change is checked against the real ledger (parsing, booking and balance assertions) on a staged copy. A change that would introduce an error is refused, leaving the ledger alone.
- Agent changes arrive as **proposals**. You review the exact postings and approve or reject them in the web interface or inside your agent harness. Nothing reaches the ledger until you approve it.

## What you get

| Part | What it does |
| --- | --- |
| **Service** | One ASGI process (FastAPI) with a REST API, an optional MCP endpoint, a small web interface, and the Beancount engine. Run it in Docker. |
| **Account types and recipes** | Built-in behaviour for checking and savings accounts, cash and wallets, credit cards (also in two currencies), loans, receivables and payables, and brokerage. |
| **Web interface** | A server-rendered page to approve or reject proposals, edit bank details and profiles, and manage credit pools. |
| **Claude Code plugin** | The MCP connection, a skill that explains how the books are modelled, a guard hook, and user-only review commands. |
| **DeepSeek Harness plugin** | Native tools, a ledger held in the session, and a right-dock page for the overview and for approvals. |
| **Fava** | Optional. Open the same ledger in Fava to read it and edit it by hand. |

## How the pieces fit

```text
 agents (MCP, native plugin tools)          you (web UI, dock page, Fava)
              │                                           │
              ▼                                           ▼
     ┌─────────────────────────── service ───────────────────────────┐
     │  MCP tools   Agent REST   REST API   Web interface            │
     │          └───────────── service layer (async) ───────────┘    │
     │             recipes · proposals · views · validation          │
     │                      Beancount engine                         │
     └───────────────────────────────┬───────────────────────────────┘
                                     ▼
                        ledger files (plain text) + sidecar
```

The agent-facing surfaces (MCP and the agent REST API) can only **propose**. Approval is a different door, reached by you, so an agent that works only through its tools has no way to approve its own change.

## Where to start

- To run it: [Quickstart](getting-started/quickstart.md), then [Create your first ledger](getting-started/first-ledger.md).
- To understand how it models money: [Ledgers](concepts/ledgers.md), [Proposals](concepts/proposals.md), [Accounts](concepts/accounts.md) and [Recipes](concepts/recipes.md).
- To connect an agent: [Claude Code](guides/claude-code.md), [DeepSeek Harness](guides/deepseek-harness.md) or [any other MCP client](guides/other-agents.md).
- For a realistic walk-through, including a credit card billed in two currencies: [Worked examples](guides/worked-examples.md).

:::caution Status
The project is young. The service, the recipes, the web interface and the two plugins work and are tested, but the API and the tool names can still change. Keep a backup of your ledger, as you would for any hand-edited file.
:::
