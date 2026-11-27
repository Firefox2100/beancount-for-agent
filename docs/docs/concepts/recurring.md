---
title: Recurring items
---

Rent, a subscription, a salary: things that happen on a schedule. A recurring item describes the schedule and the entry it produces. The service never posts one by itself, so nothing happens unattended and everything still passes through your approval.

## An item

- **Accounts.** Money moves from one account to another, as in a transfer. Rent is `Assets:Bank` to `Expenses:Rent`. A salary is `Income:Salary` to `Assets:Bank`.
- **Amount.** Each occurrence's amount. Mark an item **variable** when it changes every time (a utility bill): the amount is then an estimate and is not used to recognise a payment.
- **Schedule.** Every N weeks, months or years, from a first due date. Monthly items keep the day of the first date, and a 31st falls on the last day of shorter months. An optional last date ends it.
- **Payee and narration**, used for the entries it produces.

Items live in the sidecar profile, next to pools and account settings. Only you can add, change or remove them, in the web interface (**Recurring**) or through the REST API. An agent cannot, because it would change what the service treats as due.

## What is due

`get_recurring` (REST: `GET /ledgers/{id}/recurring?within_days=&lookback_days=`) lists each item with the occurrences that are not yet recorded: **overdue** (before today), **due** (today) and **upcoming** (within the window, 14 days ahead and 45 days back by default).

An occurrence counts as recorded when a transaction between the item's two accounts falls within three days before to fourteen days after its due date, with the item's amount unless it varies. That is how a payment you entered by hand is recognised, without any link to the item. Each transaction settles one occurrence.

## Recording one

`record_recurring` proposes the transaction. It carries `recurring` and `due` metadata, so the occurrence it settles is exact even when it was paid weeks late. A variable item needs the amount, which may be a formula such as `40.10 + 38.25`. The proposal waits for your approval like any other.

## Suggestions

`suggest_recurring` (REST: `GET /ledgers/{id}/recurring/suggestions`) looks through the history for payments between the same two accounts that repeat at a steady spacing (weekly, every two weeks, monthly, quarterly or yearly) and are not covered by an item. It needs three occurrences in a row, or two for a yearly one, and a recent one. The web interface lists them with an **Add** button.
