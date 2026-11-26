---
title: Fava
---

[Fava](https://beancount.github.io/fava/) is a web interface for Beancount. It is optional here, and a good companion: it reads and charts the ledger, and lets you edit it by hand, while the service handles what agents propose.

## Run it beside the service

Fava reads the ledger's `main.beancount`. With the Docker deployment, add a second service that mounts the same data folder. A minimal image:

```dockerfile title="fava/Dockerfile"
FROM python:3.12-slim
RUN pip install --no-cache-dir fava && useradd --create-home --uid 1000 fava
USER fava
EXPOSE 5000
CMD ["fava", "--host", "0.0.0.0", "--port", "5000", "/data/personal/main.beancount"]
```

```yaml title="compose.yaml (added next to the service)"
  fava:
    build: ./fava
    restart: unless-stopped
    ports:
      - "127.0.0.1:8422:5000"
    volumes:
      - /home/you/finance/data:/data
```

Fava follows the `include` lines of a yearly or monthly layout, so one `main.beancount` is enough. It has no login, so keep it on the loopback or behind your own authentication. Fava does not reload on its own unless told to: refresh the page, or accept its reload prompt, after you approve something.

## Editing in Fava

Because the ledger is plain text, you can edit it in Fava's editor or any text editor. The service copes with that:

- It checks the ledger's version before every write and again before committing.
- A proposal that **targets an entry you edited** (an amendment or deletion) is refused at approval rather than overwriting your edit.
- Content the service did not write (comments, hand-written directives, formatting) is preserved wherever possible.

The reconciliation is basic: it refuses on conflict instead of merging. A real three-way merge is planned.

Things only Fava can do today: change an account's **open date**, change an account's **currencies**, and add directives the operations do not cover yet (for example options or custom directives).

## Making income and liabilities read positively

Fava shows each account with its stored sign: expenses positive, income and liabilities negative. The Income Statement's *Net Profit* row simply adds the two sections, so with no income it shows your spending as a positive number, which is a loss. That is correct but easy to misread.

Fava has an option that displays income, liabilities and equity inverted. Add one line near the top of the ledger's main file:

```beancount
2010-01-01 custom "fava-option" "invert-income-liabilities-equity" "true"
```

It changes only how Fava displays them. The stored signs, and everything the service does, are unchanged.

## What you see

An account's `type` and its bank details appear as metadata, because they are metadata on its `open` line. The Trial Balance always sums to zero, because every entry does; your net worth is the Assets total less the Liabilities total, shown on the Balance Sheet.
