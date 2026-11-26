---
title: Architecture
---

## Layers

```text
            ┌──────────────┐   ┌──────────────┐   ┌────────────┐
 plugins ─▶ │ FastAPI REST │   │ FastMCP      │   │ Web UI     │ ◀─ people
            └──────┬───────┘   └──────┬───────┘   └─────┬──────┘
                   └───────────┬──────┴─────────────────┘
                    service layer (async)
                  pydantic models · business logic
                           │
                    ledger engine (Beancount)
                           │
                       ledger files
```

- Service code is async. Blocking Beancount work (parsing, booking and file I/O) runs in a worker thread and never blocks the event loop.
- Pydantic models every input, output and domain object at the service boundary. Raw Beancount directive objects do not cross it.
- Business logic lives in the service layer. FastAPI handlers, MCP tools and the web interface are thin adapters over the same services, with no divergent behaviour.
- Keep the layers separate: models, ledger engine, services, transports. Transports know nothing about Beancount internals.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/beancount_mcp/models/` | Pydantic models: operations, accounts, details, profile, changes, views. |
| `src/beancount_mcp/ledger/` | The engine: file layouts, sidecar, parsing and reading, edits, the store, validation, views. |
| `src/beancount_mcp/recipes/` | One module per account type, plus the shared helpers for lenient input and the registry. |
| `src/beancount_mcp/services/` | `LedgerService`, `ChangeService`, `ActionService`, `ProfileService`, `ViewService`, and `AgentService`, the intent layer both agent surfaces use. |
| `src/beancount_mcp/api/` | The FastAPI app, routers, auth middleware, dependencies. |
| `src/beancount_mcp/mcp_server/` | The FastMCP tool set. |
| `src/beancount_mcp/ui/` | The Jinja web interface, its session handling and templates. |
| `integrations/` | The pnpm workspace: the generated contract, the shared client, the Claude Code and DeepSeek Harness plugins. |
| `scripts/` | `export_contract.py` and `generate_docs.py`. |
| `docs/` | This documentation. |
| `tests/` | `unit_test/` (pure logic) and `integration_test/` (the API against temporary ledgers). |

## Surfaces

- The REST API (`api/`) is the complete CRUD surface for people and plugins acting as the user.
- The agent API (`api/routers/agent.py`) exposes `AgentService` intent operations to native plugins. It always acts as an agent and can only propose.
- MCP (`mcp_server/`) exposes the same operations as tools over streamable HTTP, mounted at `/mcp` in the same ASGI app.
- The web interface (`ui/`) handles approvals and settings that only a person should change.

`AgentService` holds the intent logic (account matching, choosing the recipe from the account's type, lenient amounts). A new agent operation is added there first, then to both adapters, and the contract is regenerated.

## The write path

Everything that changes a ledger is an `Operation` (`models/operations.py`): add, update or delete a transaction, open or close an account, set account details, add a directive, reconcile, or a batch. REST handlers and recipes build operations, and the proposal flow stores them. Adding an operation type means adding a model and its edit in `ledger/edit.py`. `Ledger.apply` does the rest: [the write path](../concepts/ledgers.md#how-a-write-happens).

## Conventions

- Prefer clear names and small functions. Comments explain non-obvious constraints, not what the code does.
- Everything configurable goes through `pydantic-settings`, and environment variables are read only in the settings module.
- Never build ledger text with string formatting: use Beancount's printer.
- Hashes used for identity and versions are SHA-256.
- The version comes from git through `hatch-vcs`. Do not hard-code one.

## Toolchain

Python 3.12 managed with `uv` (add dependencies with `uv add`), Beancount 3, FastAPI, FastMCP, `pydantic-settings`, Jinja2. The JavaScript workspace uses pnpm. Run the server with `uv run beancount-mcp`.

## Deployment

The `Dockerfile` builds the image (`docker build -t <tag> --build-arg VERSION=<x> .`). It listens on `0.0.0.0:8000`, keeps the ledgers in `/data`, and runs as user id 1000, so a bind-mounted data folder must be writable by that user. A compose file belongs with your deployment rather than in this repository.
