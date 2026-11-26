# beancount-for-agent

A suite of services and integrations that lets AI agents manage your finances in a [Beancount](https://beancount.github.io/) ledger, without ever editing the ledger themselves.

- Agents work through intent-shaped operations (record an expense, pay a card bill, reconcile an account). The service turns them into validated postings.
- Every agent change is a **proposal**. You review the exact postings and approve it in a web interface or inside your agent harness.
- An MCP endpoint serves any MCP client. Native plugins exist for Claude Code and DeepSeek Harness.

Read the documentation in [`docs/`](docs/), built with Docusaurus:

```bash
pnpm install
pnpm --filter beancount-mcp-docs start     # live preview
pnpm --filter beancount-mcp-docs build
```

Quick start: build the image (`docker build -t beancount-mcp:local --build-arg VERSION=0.1.0 .`), set `BEANCOUNT_MCP_AUTH_TOKEN` and `BEANCOUNT_MCP_MCP_ENABLED=true`, and run it. The documentation has the full walkthrough, including the compose file.

Development uses `uv` (`uv run pytest`) for the service and `pnpm` for the integrations and the docs.
