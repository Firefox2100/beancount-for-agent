---
title: Worked examples
---

Each example shows what you say, what the agent proposes, and what it means in the books. Amounts and names are made up.

## A current account with an opening balance

> Open a checking account `Assets:Barclays:Current` in GBP, and `Equity:Opening-Balances`. Then record an opening balance of 48,469.17 GBP.

The agent proposes two `open_account` changes. You approve them (an entry cannot use an account that is not yet open). Then it proposes:

```beancount
2026-11-25 * "Opening balance"
  Assets:Barclays:Current       48469.17 GBP
  Equity:Opening-Balances      -48469.17 GBP
```

Net worth is the Assets side less Liabilities: 48,469.17. The negative Equity balance is only where the money came from.

## An everyday expense

> I bought lunch for 12.50 from the cash wallet, under food.

`record_expense` finds the wallet is a `cash` account and uses its `spend` recipe:

```beancount
2026-11-26 * "Lunch"
  Expenses:Food       12.50 GBP
  Assets:Cash:Wallet -12.50 GBP
```

Account names can be loose (`wallet`, `food`). If more than one account matches, the agent is told the candidates and tries again.

## A credit card in two currencies

A Bank of China style card holds CNY and USD, and you spend in GBP abroad.

**Setup.** Open `Liabilities:BoC:Platinum` (type `credit_card`, currencies CNY and USD) and its sub-account `Liabilities:BoC:Platinum:Unbilled`. In the web interface set the statement day, due day and autopay account.

**A GBP purchase.** Ask for a `purchase` of 18.65 GBP at a pharmacy. It waits on the Unbilled account in its own currency:

```beancount
2026-11-24 * "Knights Dispensing Chemist" "Medicine"
  Expenses:Health:Medicine                  18.65 GBP
  Liabilities:BoC:Platinum:Unbilled        -18.65 GBP
```

**A purchase the bank converts at once**, such as 39.04 USD billed as 261.19 CNY, is recorded with the billed amount, and the original amount is kept as metadata:

```beancount
2026-11-12 * "Meta Platform" "Gaming"
  original-amount: "39.04 USD"
  Expenses:Gaming          261.19 CNY
  Liabilities:BoC:Sub     -261.19 CNY
```

**The statement.** When the bank issues it, tell the agent the amounts it billed for the unbilled purchases and it proposes `close_statement`: the GBP waiting on Unbilled is converted into the billed currency at the bank's actual figure. No gain or loss account is needed.

**Paying.** `pay_card` takes what left the debit account and what it cleared on the card, because the bank sets the rate for a payment in another currency:

```json
{
  "from_account": "Assets:BoC:Current",
  "payments": [{ "paid": "1980.50 CNY", "cleared": "1980.50 CNY" }]
}
```

A payment in another currency than the bill gives both: `"paid": "250 GBP"`, `"cleared": "2310.20 CNY"`.

If the card pays itself on the due day, set the autopay account on the card's profile and ask the agent to record the payment when it has left your account. The service does not run jobs.

## A card someone else pays

A sub-card on a parent's account whose bills the parent pays is easiest tracked as an ordinary card. When the parent pays the bill, record it as a gift:

> My parent paid the sub-card bill, 1,650.74 CNY.

`pay_card` is used with `Income:Family:Parents` as the paying account, so the liability is cleared by income rather than by your own money. Your expenses stay visible, and net worth is unaffected.

## Money you are owed

> I lent a friend 50 GBP.

A `receivable` account with the `lend` recipe opens an item with a generated link (`^claim-a1b2c3`). When they pay back, `collect` settles it, taking the link or settling everything open if you give no amount. `get_open_items` shows what is still outstanding.

## Fixing a mistake

Entries recorded with the wrong date or text can be corrected by proposal:

> The 26 November purchases were really on the 25th.

The agent finds the entries with `search_transactions` and proposes `amend_transaction` for each (date, payee, narration and tags can change). A wrong amount or account is fixed by deleting and re-recording. An account's open date cannot be changed through the tools: edit it in [Fava](fava.md).

## Checking against a statement

> My bank says the current account holds 48,420.12 on 30 November.

`reconcile_account` proposes a balance assertion for that date. If the books disagree, it is refused and shows the difference. Give a pad account (an adjustments expense, say) if you want the difference booked there instead.
