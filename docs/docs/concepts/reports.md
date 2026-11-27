---
title: Reports
---

Reports answer *how much did I spend, earn and save* without an agent adding up postings itself. They are read-only and computed from the ledger.

## Income statement

`get_income_statement` (REST: `GET /ledgers/{id}/reports/income-statement`) adds up `Income` and `Expenses` accounts over a period.

| Parameter | Meaning |
| --- | --- |
| `start`, `end` | The period. It defaults to this month so far. |
| `account` | Only this group, such as `Expenses:Food`. Its sub-accounts are then shown. A short or loose name works for agents. |
| `depth` | How many segments of the account name to group by. The default is 2 (`Expenses:Food`), or one more than `account` when one is given. |
| `interval` | Also break the totals down per `week` or `month`. |
| `compare` | Also give each account's total for the equal period before. |

Amounts stay in the currencies they were booked in and nothing is converted. Expenses and income are positive, a refund reduces an expense, and equity movements are ignored. The result includes the net (income less expenses) and, when everything is in one currency, the savings rate as a percent of income.

The web interface has a **Reports** page with the same options, preset periods and account drill-down.
