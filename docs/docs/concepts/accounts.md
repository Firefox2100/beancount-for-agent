---
title: Accounts and profiles
---

## Account names

Accounts form a tree under the five Beancount roots:

| Root | What it holds | Normal sign |
| --- | --- | --- |
| `Assets` | What you own: bank, cash, investments. | positive |
| `Liabilities` | What you owe: cards, loans. | negative |
| `Equity` | Where opening balances come from. | negative |
| `Income` | Money coming in. | negative |
| `Expenses` | Money going out. | positive |

A name looks like `Expenses:Food:Groceries`. Each component starts with a capital letter or a digit and may contain letters, digits and hyphens.

:::note Signs
Beancount stores a liability or income as a negative number. A credit card you owe 300 on shows `-300`. This is how every entry sums to zero, and Fava can display income, liabilities and equity as positive if you prefer (see [Fava](../guides/fava.md)). The stored signs should not be flipped.
:::

## Account types

An account may have a **type**, stored as `type` metadata on its `open` line, so other Beancount tools see it. The type decides which [recipes](recipes.md) the account gets.

| Type | For |
| --- | --- |
| `checking` | A current or debit account that holds money and pays for things. |
| `savings` | Savings or a fixed-rate deposit. Interest is booked as income. |
| `cash` | Physical cash. |
| `ewallet` | A prepaid balance or payment app wallet. |
| `credit_card` | A credit card, possibly billed in several currencies. |
| `loan` | Money owed in instalments: a mortgage, personal or student loan. |
| `receivable` | Money owed to you: a reimbursement claim, a loan to a person, an unpaid invoice. |
| `payable` | Money you owe on a bill or to a supplier, not yet paid. |
| `brokerage` | Investments held as commodities, with a cash account for settlement. |

Types are plain strings, so a custom one needs no declaration. An account with no type, or a type with no recipes, still works with the plain income, expense and transfer operations.

## Currencies

An account holds the currencies it was opened with. Balances in different currencies are never added together. When money changes currency, the entry states both amounts, because each bank uses its own rate. See [Recipes](recipes.md#multiple-currencies).

## The profile

The sidecar file `.sidecar/profile.toml` holds what only this service interprets:

| Field | Meaning |
| --- | --- |
| `description` | What the account is for, in your words. Agents read it to recognise the account. |
| `recipes` | Restrict which recipes the account offers. Unset means all that apply to its type. |
| `statement_day`, `due_day` | The day of the month a card's statement closes and its payment is due. |
| `autopay_from` | The account a card is paid from. |
| `pool` | The [credit pool](views.md#credit-pools) the card belongs to. |
| `unbilled_account` | Where a card's unbilled foreign purchases wait. Defaults to `<card>:Unbilled`. |
| `interest_account`, `cash_account`, `gains_account` | Defaults for the interest, brokerage settlement and gains postings. |
| `interest_rate`, `maturity_date` | Informational: nothing is calculated from them. |

Plus the pools and their limits. The profile has its own revision (a hash of the file), so a client can tell that its cached account descriptions are stale.

**Only you change the profile.** Changes are made through the web interface or the API by a `user` caller with `If-Match` on the revision. The profile refers to accounts by name, so an account renamed in Fava leaves dangling references. Loading reports these as warnings, never errors.

## Bank details

Where an account lives at its bank is stored as metadata on its `open` line, so Fava and other tools see it:

`bank-name`, `account-holder`, `branch`, `sort-code`, `account-number`, `routing-number`, `iban`, `swift-bic`, `card-number`, `card-holder` and `card-expiry`.

Values are normalised on input: a sort code becomes `20-12-34`, an IBAN is upper-cased, an expiry becomes `MM/YY`. **Nothing that authorises a payment is accepted**: there is no field for a CVV, PIN or password, and unknown fields are refused.

- Set these details on an account page in the [web interface](../guides/web-interface.md), or use `PUT /ledgers/{id}/accounts/{account}/details`. Agents are refused, and no MCP tool accepts them.
- Agents receive masked values. Sort code, account number, routing number, IBAN, card number and expiry arrive as `••••5678`. The bank name, holder, branch and SWIFT are unchanged. This is enough to recognise an account without revealing its number.
- The REST API shows them in full, to you.

## Opening and closing

Open an account from a date, optionally with a type and currencies. A closed account keeps its history. An agent proposes both with `open_account` and `close_account`.
