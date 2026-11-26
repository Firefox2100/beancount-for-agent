---
title: Proposals and approval
---

Agent changes are not applied directly. They become **proposals** that you review. This is the central safety property of the project.

## The flow

```text
agent ── proposes ──▶ validated by a dry run ──▶ stored as pending
                                                        │
              you review the exact postings ◀───────────┘
                    │                 │
                 approve            reject
                    │
        validated again, then committed
```

1. The agent submits an operation (or a recipe action) with the ledger version it last saw.
2. The service **fully validates it by a dry run** and refuses it if it is invalid. Every stored proposal was valid when it was made.
3. It is stored in `.sidecar/changes/` as `pending`. Nothing has touched the ledger.
4. You review it, with the exact postings and who proposed it, and approve or reject.
5. Approving **re-validates against the current ledger**, then commits. Independent proposals do not invalidate each other, so one approval does not stale the rest.

A proposal that targets an existing transaction or record (an amendment or a deletion) fails approval with `409` if that entry was modified after the proposal was made, and stays pending.

A resolved proposal is kept as history. The agent can **withdraw** its own pending proposals, and can list the ones it made. Proposals are private to the client that made them, so two sessions do not see each other's drafts.

## Who can approve

Not the agent. The agent-facing surfaces, the MCP tools and the `/agent` REST API, have no approve or reject operation at all. Approval is available through:

- the [web interface](../guides/web-interface.md) (`/ui/`),
- a harness plugin: the [DeepSeek Harness dock page](../guides/deepseek-harness.md) or the [Claude Code review commands](../guides/claude-code.md),
- the REST API, `POST /ledgers/{id}/changes/{change_id}/approve` and `/reject`, with a JSON body.

An agent that works only through its tools has no reason to know these exist, and the plugins keep the token out of its reach. See [Security](security.md).

## Callers

Requests identify themselves with `X-Actor` (`user` by default, or `agent`), `X-Client-Id` and `X-Session-Id`. These are for identification and for keeping drafts apart, not authentication. The bearer token is what authenticates, and it proves only that the caller may use the service.

The agent surfaces ignore `X-Actor` and always act as an agent, so they can only propose.

## Direct writes

The ordinary CRUD endpoints commit at once. With `agent_approval_required` true, the default, they refuse `X-Actor: agent` with `403`. A harness plugin whose user approved inside the harness may call them as `user`.

## Auto-approval

With `AGENT_APPROVAL_REQUIRED=false`, an agent's submission is applied at once and recorded as approved. It is validated all the same. Use it only for a ledger you are happy to let an agent write unreviewed.

## Amending and deleting

An agent can propose `amend_transaction` (date, payee, narration, tags; the postings are kept) and `delete_transaction`. To change an amount or an account, the agent deletes the entry and records it again. Both are proposals like everything else.
