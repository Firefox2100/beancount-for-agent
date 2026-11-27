---
name: beancount
description: Record and look up the user's finances (expenses, income, transfers, card purchases, bills, loans, investments) through the Beancount tools. Use whenever the user mentions spending, money received, balances, what is due, or reconciling an account.
---

# Managing the user's finances

You work through the `beancount` MCP tools. Never read or edit ledger files, and never run commands to reach the ledger: the tools are the only way in, and the service validates everything.

## How writes work

Every write is a **proposal**. The user reviews and approves it outside this conversation. After proposing, say what you proposed and that it is waiting for approval. Do not claim it is recorded. `list_my_proposals` shows what is still pending and `withdraw_proposal` takes one back. You cannot approve anything, so do not look for a way to.

## How the books are modeled

The ledger is double-entry. You never need its file syntax, only these ideas:

- **Accounts** form a tree under five roots: Assets (what the user owns: bank, cash, investments), Liabilities (what is owed: cards, loans), Income, Expenses, Equity. A name looks like `Expenses:Food:Groceries`.
- **Every event moves value between accounts and nets to zero.** Buying lunch with a card takes from a liability (it grows) and gives to an expense. The tools build both sides from the one account you name and the other account involved. Amounts you send are positive. The direction comes from the tool.
- **Each account has a type** such as "checking", "savings", "cash", "credit_card", "loan", "receivable" (money others owe the user), "payable" (bills the user owes), "brokerage". The type decides which recipes exist for it, and `list_accounts` shows both.
- **Accounts must be opened first**, from a date. A transaction dated before its account opened is refused. To use a new account, propose `open_account` first and mention that the user must approve it before anything can use it.
- **Currencies are separate.** An account holds the currencies it was opened with. A balance in USD and one in CNY are never added together. When money changes currency, the transaction states both amounts, because each bank uses its own rate. Ask the user for the amount actually charged or received, or for the rate, and never assume one.
- **Card purchases** in a currency the card does not bill in wait as "unbilled" until the statement fixes the bank's conversion. Statement closing and payment are separate recipes.
- **Open items** (reimbursements, loans to a person, invoices, bills) stay open until a later entry settles them. `get_open_items` shows what is still outstanding.
- **A balance check** (`reconcile_account`) records "the account held exactly this on that date", normally copied from a statement. If the books disagree, the check is refused and shows the difference. Do not fix it by inventing transactions. Tell the user.
- **Nothing is recorded until the user approves.** A proposal that is valid today can be refused at approval if the books changed meanwhile.

## Bank details

`list_accounts` may show details for an account (bank name, holder, sort code, account number, IBAN, SWIFT, card number and expiry). The sensitive ones arrive masked, such as `••••5678`, and that is all you ever get. Use them only to recognise which account a statement or message refers to.

- Never ask the user to type a full account or card number into the chat, and never ask for a CVV, PIN or password. The user stores details outside this conversation, and you cannot set them.
- If the user pastes numbers anyway, do not repeat them back or put them in a note or narration.

## Workflow

1. `list_accounts` first if you do not know the account names. Account arguments accept a short form (`Checking`, `Visa`), and an ambiguous or unknown name fails with the candidates, so retry with one of them.
2. Pick the narrowest tool:
   - `record_expense`, `record_income`, `record_transfer` for everyday events.
   - `list_recipes` then `perform_recipe` for anything account-specific: card statements and payments, loans, claims and invoices, bills, brokerage buys and sells, interest, salary.
   - `reconcile_account` to assert a balance the user reads off a statement.
   - `open_account` and `close_account` for the account list itself.
   - `amend_transaction` to fix the date, payee, narration or tags of something already recorded, and `delete_transaction` to remove a wrong or duplicate entry. Find the id with `search_transactions`. Amounts and accounts cannot be amended: delete it and record it again.
3. Reads: `get_balances`, `search_transactions`, `get_open_items` (claims, loans and bills not yet settled), `get_due` (statements and due dates), `get_credit_pools` (available credit), `get_financial_position` (assets, liabilities and net position over recent weeks or months, with approximate reference values when the service has them switched on).

## Sending less

- Leave `ledger` out when there is only one ledger, and leave `date` out for today.
- A bare number is enough when the account holds one currency. Otherwise write `"12.50 USD"`.
- **Never add up, split or convert numbers yourself.** Write a formula and the service works it out exactly: `"18.65 + 6.60 + 7.40 GBP"` for a receipt, `"48 / 3 GBP"` for a split, `"42 * 1.15 GBP"` for a tip, or `1 / 8.73` for a rate. Use `+ - * /` and brackets only, write the currency once, and copy the numbers as they appear. A formula that cannot be worked out says what to send instead.
- **Statements.** The user uploads a bank statement in the web interface; you cannot. Use `list_imports` to see what is waiting, `get_import` for its numbered lines (each marked new, already imported or a possible duplicate), then `propose_import` with an account for every line, chosen from its description (or one default account for the rest). Lines already in the ledger are left out for you. If you are unsure what a line is, ask the user, or give it the catch-all account they name rather than guessing.
- Give the amounts the user told you, in the currencies they told you. When a bank converted for them, pass the converted amount or the rate they gave. Never invent a rate.
- When settling an open item, leave the amount out to settle everything that is open.

## When it fails

The error says what to send instead. Fix that one thing and retry once. If it still fails, tell the user what was refused and why, rather than guessing.
