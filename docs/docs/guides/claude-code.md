---
title: Claude Code
---

The plugin in `integrations/claude-code` gives Claude Code the MCP connection, a skill that explains how the books are modelled, a guard hook, a session briefing, and **user-only** commands to review proposals. It is shell and JSON: it needs `curl` and `jq` and no Node.

## Install

The repository contains a marketplace file at `.claude-plugin/marketplace.json`. Add it and install the plugin. To use it only in one project, use local scope:

```bash
cd /path/to/beancount-for-agent
claude plugin marketplace add ./ --scope local
claude plugin install beancount@beancount-mcp --scope local
```

**Scopes.** `user` enables a plugin everywhere, `project` records it in the project's committed settings, and `local` records it for you in that project only. For a finance setup, local scope in one folder keeps the finance prompts out of your coding projects, and keeps the options (and the token) out of a committed file.

## Configure

The plugin has two options, set once:

| Option | Meaning |
| --- | --- |
| `url` | Where the service listens, for example `http://127.0.0.1:8421`. |
| `api_token` | The service token. It is a *sensitive* option, stored outside the settings files. |

Set them with `/plugin configure beancount@beancount-mcp` in Claude Code, or from a terminal:

```bash
printf '{"url":"http://127.0.0.1:8421","api_token":"<token>"}' \
  | claude plugin configure beancount@beancount-mcp --values-stdin
```

Restart Claude Code, or run `/reload-plugins`, and check `/mcp` for `beancount` connected.

## What it adds

- **MCP** (`.mcp.json`): connects to `<url>/mcp` with the token. The token reaches only the MCP connection and the plugin's hooks, not the agent's shell.
- **Skill** (`beancount`): how to record and look up finances, and how the books are modelled (accounts, double entry, account types, currencies, open items, balance checks). It tells the model that every write is a proposal and that it cannot approve.
- **Guard** (`hooks/guard.sh`, before tools run): refuses `Bash`, `Read`, `Write`, `Edit`, `Glob` and `Grep` calls that touch ledger files, the sidecar, the token or the service settings. For shell commands it checks the whole command. For file tools it checks only the target path, never the text written, so editing source code that merely mentions a ledger file is allowed. Set `BEANCOUNT_MCP_GUARD_PATHS` (colon separated) in the environment Claude Code starts from to protect more, such as the data folder. Without `jq` the guard cannot read its input and lets the call through.
- **Briefing** (`hooks/briefing.sh`, at session start): tells the model how many proposals are waiting and what is due within a week. It fails open: with the service down the session just starts without it.

## Reviewing proposals

Four commands exist only for you; the model cannot invoke them:

| Command | Does |
| --- | --- |
| `/beancount:pending` | Lists pending proposals with their exact postings. |
| `/beancount:approve LEDGER ID` | Approves one. |
| `/beancount:reject LEDGER ID [REASON]` | Rejects one, with an optional reason. |
| `/beancount:due` | Shows statements and bills due in the next two weeks. |

They run `scripts/review` inside the plugin, which calls the REST API as you. The script is deliberately not in the plugin's `bin/` folder, because Claude Code puts a plugin's `bin/` on the agent's `PATH`. You can also use the [web interface](web-interface.md) instead.

## Bank details from a terminal

Anything you type in the chat is seen by the agent, so bank details are set outside it:

```bash
export BEANCOUNT_MCP_URL=http://127.0.0.1:8421
export BEANCOUNT_MCP_TOKEN_FILE=~/finance/service/.env      # or export the token itself
S=<repository>/integrations/claude-code/scripts/review
$S details personal Assets:Barclays:Current bank_name=Barclays sort_code="20 12 34"
$S details personal Assets:Barclays:Current          # show everything, in full
$S details personal Assets:Barclays:Current -iban    # clear a field
```

The token file may hold the bare token or the service's own env file; the script reads `BEANCOUNT_MCP_AUTH_TOKEN=` from it.

## Notes

- The plugin is read from the repository folder, so edits there apply at the next session start or `/reload-plugins`.
- Tool names and schemas are a contract the plugin depends on. See [Development](../development/integrations.md).
