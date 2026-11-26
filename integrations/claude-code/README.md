# Claude Code plugin

Connects Claude Code to a running beancount-mcp service (started with `MCP_ENABLED=true`).

- **MCP**: `.mcp.json` connects to `<url>/mcp` with the service token, both set as plugin options (`url`, `api_token`). The token is stored as a sensitive option and reaches only the MCP connection and the hooks, not the agent's shell.
- **Skill** (`skills/beancount`): how the agent should record and look up finances.
- **Guard** (`hooks/guard.sh`, PreToolUse): refuses file and shell tools that touch ledger files, the sidecar, the token or the service settings. Set `BEANCOUNT_MCP_GUARD_PATHS` (colon separated) to also protect the data folder.
- **Briefing** (`hooks/briefing.sh`, SessionStart): proposals waiting and bills due within a week. Fails open.
- **Review commands**, user-only (`disable-model-invocation`): `/beancount:pending`, `/beancount:approve LEDGER ID`, `/beancount:reject LEDGER ID [REASON]`, `/beancount:due`. They run `scripts/review`, which calls the REST API. The script is deliberately not in `bin/`, which Claude Code puts on the agent's PATH.

Needs `curl` and `jq` (no Node). Tests: `pnpm test` from the repository root.

Not done yet: injecting `ledger` into tool calls with a PreToolUse `updatedInput`. Whether Claude Code applies it to MCP tool arguments is unconfirmed in its docs, so test that before relying on it. With one ledger it is unnecessary.
