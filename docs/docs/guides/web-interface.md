---
title: Web interface
---

A small server-rendered interface at `/ui/`, for what only a person should do. It is deliberately not a dashboard and not a ledger editor, and it does not replace [Fava](fava.md).

## Sign in

Open `http://<host>:<port>/ui/` and enter the service token. You get a signed, expiring cookie, so the token is never kept in the browser. With no token configured the interface is open, like the API.

## Inbox

The front page lists what is **waiting for your approval**, per ledger and oldest first. Each card shows who proposed it (`agent/mcp`, `agent/dsh`), when, the agent's note, and the **exact postings**. Add an optional note and press **Approve** or **Reject**.

If approval fails (for example the ledger changed under a proposal that edits an entry) the reason is shown on the page and the proposal stays pending.

Each ledger also links to its **history**: the last fifty resolved proposals with their notes.

## Overview

Each ledger has an **overview**, the same one the DeepSeek Harness dock shows: assets, liabilities and net position over the last twelve weeks or months, the asset allocation, what is due soon, and every account grouped by type with its balance. Valuations are approximate reference values and are never written to the ledger (see [Views](../concepts/views.md)); the **Refresh rates** button throws the rate cache away and prices the ledger again. Long numbers are written with commas, such as `123,456.78`, here and in the dock.

## Receipts

**Receipts** (per ledger) is where you upload a receipt photo or PDF, optionally linking it to a transaction. It lists what is stored and whether the ledger links it, and a stored receipt can be linked to a transaction from there. A proposal an agent makes from a receipt shows it in the inbox beside the postings. See [Receipts](../concepts/receipts.md).

## Goals

**Goals** (per ledger) lists each savings goal with a progress bar, what remains, what to put aside each month to arrive on time and when the plan reaches the target. See [Goals](../concepts/goals.md). The overview also lists **Worth a look**: errors, overdrawn accounts, stale balances and likely duplicates, see [Checks](../concepts/checks.md).

## Budgets

**Budgets** (per ledger) shows each limit with a progress bar and a marker for how far through the period you are, the projection, the daily allowance and the earlier periods. It suggests budgets from your history and has a form to add one. Budgets that are over or ahead also appear on the overview. See [Budgets](../concepts/budgets.md).

## Reports

**Reports** (per ledger) shows income and expenses over a period by account, with a month or week breakdown, an optional comparison with the period before, and drill-down into a group. See [Reports](../concepts/reports.md).

## Recurring

**Recurring** (per ledger) lists each schedule with what is overdue or coming up, repeating payments found in your history with an **Add** button, and a form to add one yourself. Items due soon also appear on the overview. See [Recurring items](../concepts/recurring.md).

## Statements

**Statements** (per ledger) is where you upload a bank file for an account. It lists what was uploaded, how many lines are still new and any warnings, and each statement opens to its numbered lines with their status. The agent then proposes the new lines for you to approve in the inbox. See [Importing statements](../concepts/imports.md).

## Accounts

The accounts of a ledger, with their type, currencies and bank. Click one for its page, which has two forms:

**Bank details.** Sort code, account number, IBAN, SWIFT/BIC, card number and expiry, and so on, shown here in full. Leave a field empty to remove it. Values are validated and normalised. Agents see the sensitive ones masked and cannot set any. See [Accounts](../concepts/accounts.md#bank-details).

**How the service treats it.** The description agents read to recognise the account, statement day and due day, credit pool, interest rate and maturity date, and the default accounts for autopay, unbilled purchases, interest, settlement and gains. Saving checks the profile's revision, so a stale page cannot overwrite a newer one.

## Credit pools

Name a pool, give its limit and currency, and put cards in it from their account pages. Clear a pool's name to remove it. See [Views](../concepts/views.md#credit-pools).

## Notes

- Every form carries a token tied to your session, and the browser's `Origin` is checked, so a page on another site cannot submit one.
- The interface calls the same services as the API and the agent tools, with no logic of its own.
- Nothing in the agent-facing text mentions it. An agent has no reason to know it exists.
