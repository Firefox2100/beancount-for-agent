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
