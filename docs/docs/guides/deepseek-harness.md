---
title: DeepSeek Harness
---

The plugin in `integrations/dsh` (`dsh-beancount`) is the fully native integration. It registers **native tools** that call the service's [agent API](../reference/agent-api.md) directly, so there is no MCP server to configure. DeepSeek Harness (DSH) plugins act as a client of their own, so this integration can hold the active ledger in the session, hide tools until you ask for them, and put approvals inside the harness.

:::caution DSH is a public beta
It breaks between patch releases. The plugin accepts `>=0.2.2-rc.1 <0.2.3-0` and is developed against `0.2.2-rc.1`. The upper bound is the lowest pre-release of 0.2.3, so the range stops before the next patch line rather than admitting its alphas. A range says what it *installs on*; it is not a promise that it was tested there. The tested releases are listed in `integrations/dsh/scripts/dsh-compat.mjs`.
:::

## Install

Install the package into a DSH profile and restart the profile (a manifest change needs a restart; a rebuilt `lib/` does not):

```bash
dsh plugin --profile <profile> add /path/to/beancount-for-agent/integrations/dsh
```

Then open **Settings > Beancount**.

## Settings

The Beancount tab of DSH's settings menu holds:

| Setting | Meaning |
| --- | --- |
| Service address | Where the service listens, for example `http://127.0.0.1:8421`. |
| Token credential name | The name of the credential holding the token. The default is `BEANCOUNT_MCP_AUTH_TOKEN`. |
| Service token | Write-only. Stored in DSH's credential store, never in the profile. The status line says whether one is stored and where from, and never shows it. |
| Request timeout | Per request, in milliseconds. |
| Guard | Refuse the assistant's file and shell tools when they touch ledger files or credentials. On by default. |
| Extra protected paths | One per line, for example the folder the ledgers live in. |

**Test the connection** reports whether the service answers and accepts the token, and lists its ledgers.

## The right-dock page

Open the right dock's guide and choose **Beancount**. It has two tabs, and refreshes when it opens, when a turn ends, and when the ledger or a tool group changes. Anything you have typed and not sent is kept across those refreshes.

- The overview contains the ledger switcher, tool-group switches and open accounts. Accounts are grouped by Assets, Liabilities, Equity, Income and Expenses, with their balances.
- The approval tab shows what is waiting, the exact postings and who proposed the change. You can add a note before choosing **Approve** or **Reject**. It lists everything pending, including what other sessions or agents proposed.

These calls are made by the DSH host as you, with the stored token. They do not appear in the conversation and the model never sees them.

## Approving in the conversation

A proposal can also be approved where it was made. After proposing a change, the model can call `finance_review`; DSH then shows a card in the conversation with the proposal's exact postings, the question and two choices, and the model waits for your answer. Choosing there records your decision through the same service call the page uses, as you.

The card is DSH's own question card, so it needs no extra permission and the plugin ships no UI for it. The page stays the place for everything still pending, for what other sessions proposed, and for approving several changes at once.

## The session holds the ledger

A conversation works on one ledger, held in the session. The model switches it with `finance_use_ledger`; you switch it in the Overview tab or with `/finance ledger <id>`. Tools never show a ledger argument. If several ledgers exist and none is chosen, a tool says so and tells the model to choose.

## Tools

All tools are prefixed `finance_`. Reading is always on; the others belong to groups you can switch per session.

| Always on | `record` group (on by default) | `analysis` group (off until you turn it on) |
| --- | --- | --- |
| `finance_ledgers`, `finance_use_ledger`, `finance_create_ledger`, `finance_accounts`, `finance_balances`, `finance_transactions`, `finance_proposals`, `finance_review` | `finance_expense`, `finance_income`, `finance_transfer`, `finance_reconcile`, `finance_recipes`, `finance_recipe`, `finance_open_account`, `finance_close_account`, `finance_amend`, `finance_delete`, `finance_withdraw` | `finance_position`, `finance_open_items`, `finance_due`, `finance_credit_pools` |

No tool can approve a change on its own. `finance_review` is the only one that ends a proposal's wait, and it does so only after you answer its card; every other write is a proposal whose reply tells the model that it is waiting for you. When a group is switched, DSH notes in the conversation that a tool was added or removed.

Switch groups in the Overview tab or with `/finance tools <record|analysis> <on|off>`. `/finance status` shows the ledger and the groups.

## Guard

A pre-call policy refuses shell and file tools whose arguments name ledger files, the sidecar, DSH's credential file, the service's environment variables, or a path you listed. Their reply tells the model to use the finance tools instead.

## Skill

The bundled `finance` skill explains how the books are modelled, for models that do not know Beancount: accounts and double entry, account types, currencies, open items, balance checks, and when to ask you rather than guess. It also tells the model never to ask for full card numbers.

## Languages

The dock page and the settings tab ship in all eight languages DSH offers — German, English, Spanish, French, Japanese, Portuguese, Russian and Chinese — and follow the harness's locale preference. The plugin's own entry in the plugin list is translated too, and has a preview image: DSH shows `docs/DETAIL.md` when it exists and falls back to `README.md` when it does not.

## Using a local model

The full tool surface is about three thousand tokens of schema, which most local models handle. The groups let you shrink it. Tool descriptions say to call a read tool for the current picture, because a small model may otherwise answer from an earlier result in the conversation.

## Development

See [Development: integrations](../development/integrations.md).
