---
title: Integrations
---

MCP is the universal, stateless surface: the service holds no per-session state and has no pinned-ledger mode. Everything a harness can do better than that, such as scoping to a ledger, hiding tools or approving inside the harness, belongs in a plugin for that harness.

## The workspace

`integrations/` is a pnpm workspace (`pnpm-workspace.yaml` and a private root `package.json`). Install with `pnpm install` and test with `pnpm test`.

| Package | What it is |
| --- | --- |
| `contract/` | The generated `openapi.json` and `mcp-tools.json`. Not a package. |
| `client` | `@beancount-mcp/client`, a dependency-free ESM client for the REST API, with a formatter for reviewing a change. Plain JavaScript with JSDoc. |
| `claude-code` | The Claude Code plugin. Node scripts and JSON. |
| `dsh` | The DeepSeek Harness plugin (`dsh-beancount`). TypeScript. |

## The contract

`integrations/contract/` is written by `uv run python scripts/export_contract.py` and checked with `--check`, which fails when the files are stale; a unit test runs it. Regenerate after changing any route, tool or schema. **Integrations are tested against these files, never against the Python code.** Tool names and schemas are a contract that plugins depend on, so changing them is a breaking change.

## Rules for a plugin

- Reach approval through the API, never MCP, and keep the bearer token out of the agent's shell and files.
- Plugin text addressed to the agent must never mention the REST API or approval commands. A test checks the Claude Code skill for this.
- A plugin installed by a harness cannot reach `../client`, so each integration is self-contained when installed. Shell plugins need no Node.
- Where a harness can mask or inject parameters, hold the active ledger in the plugin and leave it out of the model's tool schemas.

## Claude Code

`integrations/claude-code` has `.claude-plugin/plugin.json` (with the `url` and sensitive `api_token` options), `.mcp.json`, hooks (`SessionStart` briefing, `PreToolUse` guard), a skill, and user-only skills for the review commands. The review script is in `scripts/`, not `bin/`, because a plugin's `bin/` joins the agent's `PATH`.

A marketplace file at the repository root (`.claude-plugin/marketplace.json`) makes it installable from a checkout. User-only commands set `disable-model-invocation: true`.

## DeepSeek Harness

`integrations/dsh` follows `dsh-ai-providers` and `dsh-rws-tarot`: TypeScript with tsdown, vitest and Schemastery.

**Compatibility.** DSH is a public beta that breaks between patch releases. `scripts/dsh-compat.mjs` is the single source of the tested releases and the accepted range. Run `pnpm sync:dsh` in the package to write the pins and ranges into `package.json` and the workspace, and never edit them by hand. Say "tested on" only after the full pass; a range means "installs on".

**Layout of `src/`:**

| File | Role |
| --- | --- |
| `settings.ts` | Volatile settings, read with `.get()` at the moment of use. |
| `finance.ts` | The service wrapper. Resolves the token from the credential store on each call, and identifies the model's calls as an agent in its session and the page's calls as the user. |
| `format.ts` | Short plain text for the model. |
| `types.ts`, `state.ts` | Session state: the ledger and the tool groups, kept in the plugin's storage domain (`store.ts`, one record per session id); the session projection only counts ended turns, which is derived from the log. |
| `tools.ts` | The `finance_*` tools, grouped, and `finance_review`, the one that offers a pending proposal to the person as a card. |
| `review.ts` | What that card says (the exact postings, in markdown) and what the person's answer means. Rendered by DSH's own question card. |
| `guard.ts` | The `tools/pre-execute` policy. |
| `routes.ts` | What the dock page calls, as functions of a `Request`. Registered under DSH's authenticated `/api` channel. |
| `store.ts` | The storage domain the ledger and the tool groups live in. DSH's session log keeps plugin records only for its own experimental packages, so plugin data goes here. |
| `index.ts` | Registration: projection, tools with their conditions, guard, the `/finance` command, skill and routes. |
| `client/` | The right-dock page and the settings tab (React, CSS modules). |

**Why routes and not commands.** A route called by the page does not enter the session log or the conversation. Human commands are used for typed shortcuts only.

## Adding an agent operation

1. Add it to `AgentService`.
2. Add the MCP tool (`mcp_server/server.py`) and the agent route (`api/routers/agent.py`) as thin adapters.
3. Regenerate the contract and the documentation (`scripts/export_contract.py`, `scripts/generate_docs.py`).
4. Update each plugin that should expose it, and its skill. The Claude Code tests fail if the skill omits a write tool.
5. Add tests at each layer.

## Reference pages

`docs/docs/reference/` is generated: the recipes from the recipe registry, the MCP tools and both APIs from the contract. Run `uv run python scripts/generate_docs.py` after a change, and `--check` to verify. Everything else in `docs/` is written by hand.
