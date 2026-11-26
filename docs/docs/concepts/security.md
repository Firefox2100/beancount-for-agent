---
title: Security model
---

The service holds your financial data and lets software act on it, so the boundaries are explicit.

## What an agent can and cannot do

| An agent can | An agent cannot |
| --- | --- |
| Read accounts, balances and transactions. | Read or write the ledger files, directly or through the service. No tool or endpoint exposes raw file access. |
| Propose changes. | Approve, reject or amend a change, even its own. |
| Withdraw its own pending proposals. | See other clients' drafts. |
| See masked bank details. | Set bank details, change the profile or credit pools, or read a full account number. |
| Create a ledger. | Change the layout of a ledger. |

## The approval boundary is structural

There is no second credential for approval. The MCP server and the `/agent` API simply have no approve or reject operation, and the agent-facing text never mentions that the HTTP API exists. An agent that works only through its tools has no way to approve, and no reason to try. Approval happens in surfaces only you use: the web interface, a harness plugin, or the REST API with the token.

## The token

One shared bearer token, `BEANCOUNT_MCP_AUTH_TOKEN`, guards the whole service: the REST API, the agent API and the mounted MCP app. It is checked by middleware at the edge, so services never see it. It proves that the caller may use the service. It does not say who the caller is: `X-Actor` is an identification header.

The token must stay out of the agent's reach:

- Plugins give it to the MCP connection and to their own approval calls, and never put it in the agent's shell environment or files.
- The Claude Code plugin stores it as a sensitive plugin option. The DeepSeek Harness plugin keeps it in DSH's credential store, where the host resolves it for each call and never returns it.
- A blank token means no authentication. Use that only on a loopback you trust.

The web interface signs in with the same token and then uses a signed, expiring, `HttpOnly`, `SameSite=Strict` cookie scoped to `/ui`. The token itself is never kept in the browser.

## Guards in the plugins

The plugins add a second line of defence, because an agent harness usually also gives the agent a shell and file tools:

- The **Claude Code** guard hook refuses file and shell tool calls that touch ledger files, the sidecar, the token or the service settings.
- The **DeepSeek Harness** plugin refuses shell and file tool calls whose arguments name ledger files, the sidecar, DSH's credential file, the service environment, or paths you configure.

These are blunt text checks. A false refusal costs a retry; a miss would cost the boundary, so they err towards refusing.

## Masking and what is never stored

Sensitive bank details reach agents only as a mask. Fields that authorise a payment (CVV, PIN, passwords) are not accepted anywhere, and the agent skills tell the model never to ask for them or to repeat numbers a user pastes.

## Validation protects the books, too

Every write is validated on a staged copy and refused if it introduces an error. A confused or malicious proposal cannot leave the ledger in a state Beancount rejects, and cannot be approved if the ledger moved on in a way that conflicts.

## What is out of scope

- The service does not provide TLS. Put it behind something that does if it leaves the machine.
- There is one user. Per-user permissions are not modelled.
- A local model or a hosted one sees whatever the tools return. Masking limits that, and the choice of model is yours.
