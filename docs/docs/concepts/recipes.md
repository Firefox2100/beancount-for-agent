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

- The `date` defaults to today.
- An amount may be an object, text such as `"12.50 USD"`, or a bare number when the account holds exactly one currency. The recipe knows the direction, so it ignores the sign. Zero is refused.
- **Formulas.** Wherever an amount or a rate is expected, text may be a formula with `+ - * /` and brackets, such as `18.65 + 6.60 + 7.40 GBP`, `48 / 3 GBP` or `1 / 8.73`. The service works it out exactly with decimal arithmetic, so an agent copies the numbers it sees instead of adding them up. The currency is written once (or repeated identically), and two different currencies in one formula are refused. The result is rounded half-even to the most decimal places written in the formula, and to at least two (a rate keeps up to eight). Exponents, percent signs, powers, names and functions are not accepted.
- For two linked amounts, you may send either value. Examples include a converted amount or a `rate`, gross or net pay, principal or total repayment, and price per unit or total.
- Defaults come from the profile when available, including the autopay source, interest account, cash account and gains account. The error names any missing setting.
- Agent tools match account names loosely. They try an exact name, a case-insensitive match, a unique trailing segment (`Checking`, `Bank:Checking`), then a unique word in the name or description. Ambiguous and unknown names fail with a list of candidates. The user-facing REST API stays strict.
- Errors explain what to send next, not only what went wrong.

## Multiple currencies

Each transaction carries its own rate, because every bank and service offers a different one. A `rate` is "the other currency per one unit of this one", rounded to two decimals. When you give the amount the bank actually used instead, nothing is rounded and no rate is assumed.

A transaction with a price shows whole amounts with two decimals. Beancount gives whole numbers no balancing tolerance, and a price computed by division would otherwise leave a rounding residue that fails validation.

## Credit cards in more than one currency

This is the case the recipes were built against. A card can hold balances in two currencies, say USD and CNY, and a purchase in a third (GBP) can be billed three ways: in the original currency, converted to one billing currency at purchase, or converted when the statement is issued.

- A purchase in a billing currency of the card posts straight to the card's liability.
- A purchase in another currency posts to an **`Unbilled` sub-account** in its own currency, because the bank's conversion is not known until the statement.
- `close_statement` converts the unbilled amount into the billed currency at the bank's actual figure. Beancount balances this with a total price, so no gain or loss account is needed.
- `pay_card` clears a bill in either currency, or both. You provide the amount debited and the amount cleared because the bank sets the rate.
- When a card converts a foreign purchase at purchase time (the `billed_amount` of `purchase`), the entry records the billed amount on both sides and keeps the original amount as `original-amount` metadata.

Autopay is configuration, not a scheduler: the profile records the source account and the due day, and a harness polls [`get_due`](views.md) and proposes the payment. The service never runs jobs. See [Worked examples](../guides/worked-examples.md).

## Open items

A reimbursement claim, a loan to a person, an invoice and a bill to pay are one mechanism. One transaction opens an item on a `receivable` or `payable` account, and a later one settles it. Both carry a Beancount **link** (`^claim-a1b2c3`), so you see the same matching in Fava.

- Recipes that open an item generate the link themselves, so the agent needs no identifier. Settling takes the link when the agent has it.
- `collect` and `pay_bill` settle everything open when no amount is given, and can forgive or discount part of it to an adjustment account.
- An item is open while its linked postings do not net to zero. [`get_open_items`](views.md) lists them.

## Extending the recipes

Built-in recipes use the same interface as extensions. A recipe has an id, a title, the account types it applies to, a pydantic parameter model (its JSON schema is what agents see) and `compile(params, context)`, which returns one operation. The context is read-only: the account, its profile, the ledger's accounts and their balances.

- Python plugins register recipes through the `beancount_mcp.recipes` entry point group. The entry point is a callable that receives the registry. Whoever deploys the service installs the plugins; agents cannot install them. Plugin output still passes validation.
- Declarative recipes are written as data in the ledger's profile, below. An agent may draft one as a proposal for you to approve, because the data cannot run code. Python plugins are never accepted through a tool.

## Recipes as data

A recipe can be written as data instead of code. It names its parameters and the postings they produce, and nothing else. It is saved in the ledger's profile, so it belongs to that ledger, and it appears next to the built-in recipes for the account types it names.

```json
{
  "title": "Bank fee",
  "description": "A fee the bank took from this account.",
  "kinds": ["checking"],
  "params": { "fee": { "type": "amount", "description": "What was taken." } },
  "narration": "Bank fee",
  "postings": [
    { "account": "@self", "amount": "-$fee" },
    { "account": "Expenses:Fees", "amount": "$fee" }
  ]
}
```

- **Parameters** have a type: `account` (optionally `under` some account types), `amount`, `text`, `date`, `number` or `tags`. They are required unless they have a default. `date` is always there and defaults to today. The JSON schema agents see is built from this, like any recipe's.
- **Postings.** The account is `@self` (the account the action is performed on), `$name` (an account parameter) or a fixed account name. The amount is `$name`, `-$name`, or absent for the rest of the entry, so it balances. At most one posting may leave its amount out.
- **Amounts** go through the same leniency as built-in recipes: the sign is ignored, formulas are worked out, and a bare number needs an account with one currency.
- **Text** (`payee`, `narration`) may use `{name}` for a text, account or number parameter, and `{name}` for an amount in the narration.
- **There is nothing else.** No arithmetic, conditions or loops, so a definition cannot become a program. If a recipe needs more, it is a Python plugin.

A definition is checked when it is saved: parameters used must exist, amounts must be amount parameters, it cannot reuse a built-in recipe's id, and a parameter a posting needs cannot be optional. The profile also warns when a definition names an account that is not open.

You define one with `PUT /ledgers/{id}/recipe-definitions/{id}`, and try it first with `POST .../preview`, which shows the transaction it would record without saving or writing anything. An agent drafts one with `preview_recipe` and `propose_setup`: see [Setting things up](setup.md).
