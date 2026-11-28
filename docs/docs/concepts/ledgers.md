---
title: Ledgers
---

## One folder per ledger

The service keeps any number of ledgers. Each one is a folder, `<data_dir>/<ledger id>/`, with a `main.beancount` at its top level. Ledgers are isolated from each other, and every operation names the ledger it applies to. (Agents may leave the name out when there is exactly one ledger.) The service assumes one user with any number of clients, such as several agent harnesses each running several sessions. Clients are not separate tenants.

The file system is the source of truth. The service starts with an empty data folder, and a ledger appears when you create one or copy a folder in.

## The code decides the file structure

Callers describe *what* to change, never *where* in the text. The service picks the file, the order and the formatting. That is what lets it promise that it never corrupts or reorders your hand-written content.

## Three layouts

A ledger uses exactly one layout, chosen when it is created.

| Layout | Files |
| --- | --- |
| `single` | One file holding everything. |
| `yearly` | `main.beancount` (entry point and options), `accounts.beancount` (account configuration), `transactions/YYYY.beancount`. |
| `monthly` | The same, with `transactions/YYYY-MM.beancount`. |

A ledger's layout is fixed once chosen. Opening an existing folder accepts any of the three. A directory with no sidecar is adopted on first open if its files match one of them exactly, trying the configured layout first. Anything that does not match is refused, not converted.

## The sidecar

State that only this service interprets lives in a `.sidecar/` folder inside the ledger, and is excluded from the ledger's version:

| File | Holds |
| --- | --- |
| `layout.json` | The layout the ledger was created with. It is authoritative. |
| `profile.toml` | How the service treats each account: descriptions, statement and due days, autopay source, credit pools. See [Accounts](accounts.md). |
| `changes/*.json` | Proposals, pending and resolved. See [Proposals](proposals.md). |

The boundary rule: if other Beancount tools would behave better knowing something, it belongs in the ledger. If only this service interprets it, it belongs in the sidecar. So an account's *type* is metadata on its `open` line, where Fava can see it, while its billing day is in the sidecar.

## Versions

A ledger's version is a SHA-256 hash of its files. Writes accept an `If-Match` header with the last version the caller saw and are refused with `412` if it is stale. A proposal records the version it was made against, and is validated again when approved.

## How a write happens

Every write goes through one path:

1. Take the per-ledger lock and check the expected version.
2. Copy the ledger files to a staging directory and apply the edit there.
3. Reload and validate: parse errors, booking, balance assertions, plugins.
4. If the edit introduces any error that was not already present, refuse it with `422` and the list of errors. The ledger is untouched.
5. Otherwise replace the changed files atomically, after checking the version once more.

Text that reaches the ledger is validated (no control characters, patterns for accounts, currencies and tags) and Beancount's own printer does the quoting. Entries without an `id` are given a stable content-based id on read. Entries the service writes carry an `id` metadata entry, and edits locate an entry by its line, so neighbouring comments and entries are left alone.

## Editing alongside Fava

You can open the same ledger in Fava. The service notices when files change under it:

- **A change in flight is computed again.** A change is worked out on a copy of the ledger files. If a file changed while it was being prepared (you saved in Fava at that moment), it is simply worked out again on what is there now, up to three times, so both edits survive. A caller that pinned a version with `If-Match` gets the conflict instead, because it asked for exactly that state.
- **An entry you edited is protected.** A proposal that updates or deletes an entry you edited by hand since it was proposed is refused at approval, rather than silently overwriting your edit.
- **Comments and hand-written entries are left alone.** Edits are made by position in the file, so what the service did not write stays as it was.

See [Fava](../guides/fava.md).

## What is supported

Transactions, balance assertions, pads, prices, commodities, notes, events, documents (as [receipts](receipts.md)), saved queries and `custom` entries, opening and closing accounts, and a few ledger options. A `batch` groups several additions into one atomic change.

- **Saved queries** (`query`) are stored with a name and the query text. The service never runs them: Fava does.
- **Custom entries** (`custom`) hold a type and typed values (string, number, amount, account, date or true/false), which other Beancount tools such as Fava read.
- **Options** are changed with `PUT /ledgers/{id}/options/{name}` and read with `GET /ledgers/{id}/options`. Only the safe ones are supported: `title`, `operating_currency` (which may be set several times: setting adds one, `remove` takes one away), `render_commas` and `booking_method`. Only that option's line in the main file is touched. Agents propose them like any other change.
- Not supported: `plugin`, `include` and the other options, which change how the ledger is read and belong to whoever runs it.
