---
title: Budgets
---

A budget is a spending limit on an expense group for a period. It is a reference, not a control: it blocks nothing and posts nothing. The service works out how it is going, so an agent never adds up spending or does the pace arithmetic itself.

## A budget

- **Account.** An expense account or group, such as `Expenses:Food`. Everything under it counts.
- **Limit.** An amount in one currency per period.
- **Period.** A week (Monday to Sunday), a calendar month, or a calendar year. A month may start on another day, 1 to 28, for a pay cycle: a start day of 25 makes each period run from the 25th to the 24th.

Budgets live in the sidecar profile and only you can add, change or remove them, in the web interface (**Budgets**) or through the REST API. An agent cannot, because that would let it change the limits it is judged against.

## How it is going

`get_budgets` (REST: `GET /ledgers/{id}/budgets`) gives each budget's current period:

- **spent**, **remaining** (negative once over), the percent used and the days left;
- **state**: `over` once past the limit, `ahead` when the share of the limit spent is more than ten points ahead of the share of the period gone, otherwise `ok`;
- **projected**: where the period ends at the current pace;
- **daily allowance**: what can still be spent per remaining day;
- **conversion**: spending under the account in other currencies is converted into the limit's currency at today's rate, so the budget is one number. `approximate` is then true, and `converted` shows each amount, the rate, its value and where the rate came from. Rates come from the reference rates when they are enabled, and otherwise from the ledger's own `price` directives (the latest on or before today). A currency with neither is listed under **other currencies** and not counted;
- **history**: the three periods before, and which went over.

Conversion uses today's rate for the whole period, which is approximate by nature and never touches an entry. Over-budget items come first. Items that are over or ahead also appear on the web overview.

## Suggestions

`suggest_budgets` (REST: `GET /ledgers/{id}/budgets/suggestions`) proposes a monthly budget for each expense group (two name segments) with spending in at least two of the last three whole months and no budget yet. The limit is the average, rounded up to the next 5 (under 100), 10 (under 500) or 50. The web interface lists them with an **Add** button.
