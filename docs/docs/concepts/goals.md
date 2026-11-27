---
title: Goals
---

A goal is something to save up for: a target amount held in some accounts, optionally by a date. Progress is what those accounts hold, so there is nothing to record by hand and nothing to keep in step. It is a reference, not a control.

## A goal

- **Accounts.** Asset accounts or groups whose balances count, such as `Assets:Savings`.
- **Target.** An amount in one currency.
- **By** (optional). The date it should be reached.
- **Monthly** (optional). What you plan to put aside each month. It is used only to say when the target is reached.

Goals live in the sidecar profile, and only you can add, change or remove them, in the web interface (**Goals**) or through the REST API.

## How it is going

`get_goals` (REST: `GET /ledgers/{id}/goals`) gives, for each goal:

- what is **saved**, what **remains** and the percent;
- with a deadline, the **months left** and the amount **needed per month** to arrive on time;
- with a planned monthly amount, when the target is **projected** to be reached;
- a **state**: `reached`; `on_track` when the plan arrives on time; `behind` when it does not, or when the deadline has passed unmet; `open` when there is no deadline, or a deadline but no plan to judge by.

Holdings in other currencies are converted into the target's currency at today's rate, as budgets are, flagged `approximate` with each conversion listed. A currency with no rate is listed separately and not counted. The arithmetic is a straight line: no forecasting method is involved.
