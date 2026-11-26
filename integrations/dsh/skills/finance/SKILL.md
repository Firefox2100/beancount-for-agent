---
name: finance
description: Record and look up the user's finances (expenses, income, transfers, card purchases, bills, loans, investments) with the finance tools. Use whenever the user mentions spending, money received, balances, what is due, or reconciling an account.
---

# Managing the user's finances

You work through the `finance_*` tools. They are the only way in: never read or edit ledger files, and never run commands to reach the ledger.

## How writes work

Every write is a **proposal**. The user reviews and approves it in the Beancount page beside the conversation. After proposing, say what you proposed and that it is waiting for approval. Do not claim it is recorded. `finance_proposals` shows what is still pending and `finance_withdraw` takes one back. You cannot approve anything.

## How the books are modeled

The ledger is double-entry. You never need its file syntax, only these ideas:

- **Accounts** form a tree under five roots: Assets (what the user owns: bank, cash, investments), Liabilities (what is owed: cards, loans), Income, Expenses, Equity. A name looks like `Expenses:Food:Groceries`.
- **Every event moves value between accounts and nets to zero.** Buying lunch with a card takes from a liability (it grows) and gives to an expense. The tools build both sides from the accounts you name. Amounts you send are positive. The direction comes from the tool.
- **Each account has a type** such as checking, savings, cash, credit_card, loan, receivable (money others owe the user), payable (bills the user owes), brokerage. The type decides which actions exist for it. `finance_accounts` shows both.
- **Accounts must be opened first**, from a date. An entry dated before its account opened is refused. To use a new account, propose it with `finance_open_account` and tell the user it must be approved before anything can use it.
- **Currencies are separate.** An account holds the currencies it was opened with. A balance in GBP and one in CNY are never added together. When money changes currency, the entry states both amounts, because each bank uses its own rate. Ask the user for the amount actually charged or received, or for the rate, and never assume one.
- **Card purchases** in a currency the card does not bill in wait as "unbilled" until the statement fixes the bank's conversion. Closing a statement and paying it are separate actions.
- **Open items** (reimbursements, loans to a person, invoices, bills) stay open until a later entry settles them. `finance_open_items` shows what is still outstanding.
- **A balance check** (`finance_reconcile`) records "the account held exactly this on that date", normally copied from a statement. If the books disagree it is refused and shows the difference. Do not fix it by inventing entries. Tell the user.
- **Nothing is recorded until the user approves.** A proposal that is valid today can be refused at approval if the books changed meanwhile.

## Bank details

`finance_accounts` may show details for an account (bank name, holder, sort code, account number, IBAN, SWIFT, card number and expiry). The sensitive ones arrive masked, such as `••••5678`, and that is all you ever get. Use them only to recognise which account a statement or message refers to.

- Never ask the user to type a full account or card number into the chat, and never ask for a CVV, PIN or password. The user stores details outside this conversation, and you cannot set them.
- If the user pastes numbers anyway, do not repeat them back or put them in a note or narration.

## Workflow

1. If a tool says several ledgers exist, ask which one, then call `finance_use_ledger`. With one ledger nothing is needed.
2. Call `finance_accounts` first if you do not know the account names. Account arguments accept a short form (`Current`, `Visa`), and an ambiguous or unknown name fails with the candidates, so retry with one of them.
3. Pick the narrowest tool:
   - `finance_expense`, `finance_income`, `finance_transfer` for everyday events.
   - `finance_recipes` then `finance_recipe` for anything account-specific: card statements and payments, loans, claims and invoices, bills, brokerage buys and sells, interest, salary.
   - `finance_reconcile` to assert a balance the user reads off a statement.
   - `finance_open_account` and `finance_close_account` for the account list itself.
   - `finance_amend` to fix the date, payee, narration or tags of something recorded, and `finance_delete` to remove a wrong or duplicate entry. Find the id with `finance_transactions`. Amounts and accounts cannot be amended: delete it and record it again.
4. Reads: `finance_balances`, `finance_transactions`, and when switched on `finance_open_items`, `finance_due`, `finance_credit_pools`. Call a read tool for the current picture rather than relying on an earlier result.

## Sending less

- Leave `date` out for today.
- A bare number is enough when the account holds one currency. Otherwise write `"12.50 GBP"`.
- Give the amounts the user told you, in the currencies they told you. When a bank converted for them, pass the converted amount or the rate they gave. Never invent a rate.
- When settling an open item, leave the amount out to settle everything that is open.

## When it fails

The error says what to send instead. Fix that one thing and retry once. If it still fails, tell the user what was refused and why, rather than guessing.
