---
title: Setting things up
---

Besides entries, a ledger has settings that decide how the service treats it: its [recipes](recipes.md) written as data, its [recurring items](recurring.md), [budgets](budgets.md) and [goals](goals.md). They live in the ledger's profile, and you can change them in the web interface or through the API.

An agent can also **propose** them. That is useful in a conversation: "rent is 1,200 on the 1st", "keep food under 300 a month", "add a recipe for the bank's monthly fee". The agent drafts the item, you read exactly what it would set, and you approve or reject it like any other change.

## How it works

1. `get_setup` shows what can be set up of one kind: the schema of an item, and the items that exist.
2. For a recipe, `preview_recipe` tries the draft on an account with sample parameters and shows the transaction it would record, so the agent can test it before asking you. Nothing is saved.
3. `propose_setup` proposes the item (or, leaving out the value, its removal). The proposal is checked first, so you are never asked to approve something that could not be saved.
4. The inbox shows the item in plain lines: a recipe's parameters and posting pattern, a budget's account and limit. Approving saves it.

## Rules

- **It always waits for you.** Even when agent changes to the ledger are applied without approval, a setup proposal never is, because it changes how the ledger is treated and not just what is in it.
- **Agents never write settings directly.** `PUT` and `DELETE` on these items are for users.
- **The same checks apply** to a proposal and to a person saving the same item.
- **Data only.** A recipe definition cannot run code. A Python plugin is installed by whoever runs the service, never through a tool.
