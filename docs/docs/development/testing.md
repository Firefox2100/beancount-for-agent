---
title: Testing
---

## Python

```bash
uv run pytest
```

Tests live under `tests/`, which is not a package, in one folder per kind:

- `tests/unit_test/`: pure logic (models, rendering, layout, configuration, recipe helpers, views, details, resolution) with no HTTP.
- `tests/integration_test/`: the API, the agent API, the MCP tools and the web interface against real **temporary** ledgers. `integration_test` is a package because it has shared helpers.

Never test against a real ledger. Shared fixtures go in the `conftest.py` of the level they serve, and helper modules sit beside it, never imported from `conftest`. Tests use `httpx2` (the replacement for `httpx`) through FastAPI's test client, and a MCP client from `fastmcp` for the tool layer.

New behaviour needs a test at the layer it lives in. A web page needs a case in `test_ui.py`; a recipe needs cases for the lenient input paths and a check that the ledger is still healthy afterwards.

## The generated files are tested

Two generated artefacts are checked for staleness:

```bash
uv run python scripts/export_contract.py --check   # integrations/contract/
uv run python scripts/generate_docs.py --check     # docs/docs/reference/
```

The contract check also runs inside `pytest`. Regenerate by running the scripts without `--check` and commit the result.

## JavaScript

```bash
pnpm install
pnpm test
```

This runs every package in `integrations/`:

- `client`: the shared REST client, against a stub fetch.
- `claude-code`: the plugin's scripts and hooks, against a stub HTTP service. The skill is checked against the contract: every tool it names must exist, and it must mention every write tool.
- `dsh`: the DeepSeek Harness plugin, against a stub service: state, guard, tools, routes and the service wrapper. No DSH installation is needed.

## Checking the DSH plugin against DSH

The unit tests cannot prove the plugin loads in the harness. `integrations/dsh/scripts/dev.sh` runs a development profile (`beancount-dev`) on its own port. Point the profile's `beancount` entry at a throwaway service, never at real ledgers. A rebuilt `lib/` hot-reloads; a manifest change needs a restart.

## Documentation

```bash
cd docs
pnpm build
```

The build fails on a broken link. See [Integrations](integrations.md) for what the `reference/` pages are generated from.
