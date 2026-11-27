---
name: finance
description: Record and look up the user's finances (expenses, income, transfers, card purchases, bills, loans, investments) with the finance tools. Use whenever the user mentions spending, money received, balances, what is due, or reconciling an account.
---

# Managing the user's finances

You work through the `finance_*` tools. They are the only way in: never read or edit ledger files, and never run commands to reach the ledger.

## How writes work

Every write is a **proposal**. The user approves it, either in the Beancount page beside the conversation or on a card you offer right here. After proposing, say what you proposed and that it is waiting for approval, and do not claim it is recorded. `finance_proposals` shows what is still pending and `finance_withdraw` takes one back. You cannot approve anything.

`finance_review` turns one pending proposal into a card in the conversation, with its exact postings, and records whichever choice the user makes there. Offer it right after proposing, while the user is present: pass the proposal id from the tool result and `language` (the language the user writes in, so the card's fixed wording matches). You cannot word the card's question or its buttons, only add a short remark with `says`, which the card shows as yours. The card blocks until the user answers, so do not call it when they are away. If they dismiss it, ask what they want instead. The page stays the place for everything proposed by other sessions and for approving several at once.

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
4. Reads: `finance_balances`, `finance_transactions`, and when switched on `finance_open_items`, `finance_due`, `finance_credit_pools`, and `finance_position` for the net position over time with approximate reference values (it needs the analysis group switched on and a ledger with an operating currency). Call a read tool for the current picture rather than relying on an earlier result.
5. After proposing, offer the approval card with `finance_review` when the user is there, unless they said they prefer the page. Say what you proposed in the same message: the card shows the postings and asks the question, and nothing is recorded until they choose.

## Sending less

- Leave `date` out for today.
- A bare number is enough when the account holds one currency. Otherwise write `"12.50 GBP"`.
- **Never add up, split or convert numbers yourself.** Write a formula and the service works it out exactly: `"18.65 + 6.60 + 7.40 GBP"` for a receipt, `"48 / 3 GBP"` for a split, `"42 * 1.15 GBP"` for a tip, or `1 / 8.73` for a rate. Use `+ - * /` and brackets only, write the currency once, and copy the numbers as they appear. A formula that cannot be worked out says what to send instead.
- **Statements.** The user uploads a bank statement in the web interface; you cannot. Use `finance_statements` to see what is waiting and its numbered lines (each marked new, already imported or a possible duplicate), then `finance_import` with an account for every line, chosen from its description (`categories`, with `default_account` for the rest). Lines already in the ledger are left out for you. If you are unsure what a line is, ask the user, or give it the catch-all account they name rather than guessing.
- Give the amounts the user told you, in the currencies they told you. When a bank converted for them, pass the converted amount or the rate they gave. Never invent a rate.
- When settling an open item, leave the amount out to settle everything that is open.

## When it fails

The error says what to send instead. Fix that one thing and retry once. If it still fails, tell the user what was refused and why, rather than guessing.
