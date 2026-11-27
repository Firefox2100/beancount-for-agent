# Beancount for DeepSeek Harness

Manage Beancount ledgers from DSH through a running beancount-mcp service. The plugin is native: its tools call the
service's `/agent/*` HTTP surface directly, with no MCP server to configure.

- **Tools** (`finance_*`): read accounts, balances and transactions; record expenses, income and transfers; run
  account-specific actions (card statements, loans, bills, trades); open and close accounts; amend or delete an entry.
  Every write is a proposal. No tool of the model can approve one: `finance_review` offers it as a card in the
  conversation and records the choice you make there.
- **Session ledger**: the conversation works on one ledger, held in the session. The model switches it with
  `finance_use_ledger`; you switch it in the page or with `/finance ledger <id>`. Tools never show a ledger argument.
- **Tool groups**: `record` (on by default) and `analysis` (off until you turn it on) can be switched per session, in
  the page or with `/finance tools <group> <on|off>`. DSH notes in the conversation when a tool appears.
- **Guard**: shell and file tools are refused when their arguments name ledger files, the sidecar, the DSH credential
  file or the service's environment. Add more paths in the `guardPaths` setting, such as the data folder.
- **Skill** (`finance`): how the books are modelled, for models that do not know Beancount.
- **Page** (right dock): overview of the active ledger, and approving or rejecting everything still pending, including
  what other sessions proposed. These calls are made by the host as you, with the stored token, and never appear in the
  conversation.
- **Approval card**: `finance_review` puts one pending proposal in the conversation as a card, with its exact postings,
  and records your answer. It uses DSH's own question card, so it needs no permission of its own and adds no UI to the
  plugin; the model waits for your choice and cannot answer for you.
- **Languages**: the page and the settings tab are translated into every language the harness ships (English, Chinese,
  Japanese, Spanish, French, German, Russian and Portuguese); `locale/*.json` gives each language the plugin's listing text.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `baseUrl` | `http://127.0.0.1:8421` | Where the service listens. |
| `tokenRef` | `BEANCOUNT_MCP_AUTH_TOKEN` | Name of the credential holding the service token. The value lives in DSH's credential store, never in the profile. |
| `timeoutMs` | `15000` | Per request. |
| `guard` | `true` | Refuse tool calls that reach the ledger or the credentials. |
| `guardPaths` | none | Extra paths to protect. |

## Compatibility

DSH is a public beta that breaks between patch releases. `scripts/dsh-compat.mjs` lists the tested releases and the
accepted range; run `pnpm sync:dsh` after editing it. A range says what the package installs on, not what it was tested on.

## Development

`pnpm test` runs the unit tests against a stub service. `scripts/dev.sh start` runs a `beancount-dev` profile on port
38092; point its `beancount` entry at a throwaway service, never at real ledgers.
