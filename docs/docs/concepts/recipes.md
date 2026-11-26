---
title: Recipes
---

Agents should not build raw postings for everyday events. A **recipe** is a small, intent-shaped action whose parameters depend on the account. It turns a few parameters into the full set of postings (several currencies, pending conversions, settlement) and returns an ordinary operation. Validation, versioning and approval are unchanged, and a proposal stores the compiled postings, so you approve exactly what will be written.

The [recipe reference](../reference/recipes.md) lists every type and recipe with its parameters. In short:

| Type | Recipes |
| --- | --- |
| `checking`, `savings`, `cash`, `ewallet` | `spend`, `receive`, `transfer`, `interest`, `salary` |
| `credit_card` | `purchase`, `refund`, `close_statement`, `pay_card` |
| `loan` | `drawdown`, `repay` |
| `receivable` | `lend`, `invoice`, `collect` |
| `payable` | `receive_bill`, `pay_bill` |
| `brokerage` | `buy`, `sell`, `dividend` |

An agent discovers what an account can do with `list_recipes` and performs one with `perform_recipe`. For the commonest events it has shortcuts, `record_expense`, `record_income` and `record_transfer`, which pick the right recipe from the account's type and fall back to a plain two-posting entry for accounts with none. The number of tools does not grow with the number of account types.

## Lenient input

Agents fail on avoidable details, so recipes ask for the least and do the arithmetic themselves:

- **`date`** defaults to today.
- **An amount** is an object, text such as `"12.50 USD"`, or a bare number when the account holds exactly one currency. The sign is ignored, because the recipe knows the direction. Zero is refused.
- **Linked amounts**: where two amounts are related, either is accepted. A converted amount or a `rate`; gross or net pay; principal or total repayment; price per unit or total.
- **Defaults** come from the profile when it has them (autopay source, interest account, cash account, gains account). The error names the missing setting when it does not.
- **Account names** in the agent tools are matched loosely: an exact name, then a case-insensitive one, then a unique trailing segment (`Checking`, `Bank:Checking`), then a unique word in the name or description. An ambiguous or unknown name fails with the candidates listed. The REST API for people stays strict.
- **Errors say what to send instead**, not just what was wrong.

## Multiple currencies

Each transaction carries its own rate, because every bank and service offers a different one. A `rate` is "the other currency per one unit of this one", rounded to two decimals. When you give the amount the bank actually used instead, nothing is rounded and no rate is assumed.

A transaction with a price shows whole amounts with two decimals. Beancount gives whole numbers no balancing tolerance, and a price computed by division would otherwise leave a rounding residue that fails validation.

## Credit cards in more than one currency

This is the case the recipes were built against. A card can hold balances in two currencies, say USD and CNY, and a purchase in a third (GBP) can be billed three ways: in the original currency, converted to one billing currency at purchase, or converted when the statement is issued.

- A purchase in a billing currency of the card posts straight to the card's liability.
- A purchase in another currency posts to an **`Unbilled` sub-account** in its own currency, because the bank's conversion is not known until the statement.
- **`close_statement`** converts the unbilled amount into the billed currency at the bank's actual figure. Beancount balances this with a total price, so no gain or loss account is needed.
- **`pay_card`** clears a bill in either currency, or both. Both the amount debited and the amount cleared are given, because the bank sets the rate.
- When a card converts a foreign purchase at purchase time (the `billed_amount` of `purchase`), the entry records the billed amount on both sides and keeps the original amount as `original-amount` metadata.

Autopay is configuration, not a scheduler: the profile records the source account and the due day, and a harness polls [`get_due`](views.md) and proposes the payment. The service never runs jobs. See [Worked examples](../guides/worked-examples.md).

## Open items

A reimbursement claim, a loan to a person, an invoice and a bill to pay are one mechanism. One transaction opens an item on a `receivable` or `payable` account, and a later one settles it. Both carry a Beancount **link** (`^claim-a1b2c3`), so you see the same matching in Fava.

- Recipes that open an item generate the link themselves, so the agent needs no identifier. Settling takes the link when the agent has it.
- `collect` and `pay_bill` settle everything open when no amount is given, and can forgive or discount part of it to an adjustment account.
- An item is open while its linked postings do not net to zero. [`get_open_items`](views.md) lists them.

## Extending the recipes

Built-in recipes use the same interface as extensions. A recipe has an id, a title, the account types it applies to, a pydantic parameter model (its JSON schema is what agents see) and `compile(params, context)`, which returns one operation. The context is read-only: the account, its profile, the ledger's accounts and their balances.

- **Python plugins** register recipes through the `beancount_mcp.recipes` entry point group. The entry point is a callable that receives the registry. Plugins are installed by whoever deploys the service, never by agents, and are trusted code. Their output still passes validation.
- **Declarative recipes** (data files with posting patterns) are planned. An agent may draft one as a proposal that you approve, since data cannot run code. Python plugins are never accepted through a tool.
