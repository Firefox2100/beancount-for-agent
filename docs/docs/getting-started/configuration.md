---
title: Configuration
---

Settings are read with `pydantic-settings`. Every variable starts with `BEANCOUNT_MCP_`. Real environment variables win over the env file.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `BEANCOUNT_MCP_DATA_DIR` | `data` | The folder holding every ledger. Each ledger is `<data_dir>/<ledger id>/`. In the Docker image it is `/data`. |
| `BEANCOUNT_MCP_LAYOUT` | `yearly` | The file layout for **new** ledgers: `single`, `yearly` or `monthly`. See [Ledgers](../concepts/ledgers.md). |
| `BEANCOUNT_MCP_HOST` | `127.0.0.1` | The address to listen on. The Docker image sets `0.0.0.0`. |
| `BEANCOUNT_MCP_PORT` | `8000` | The port to listen on. |
| `BEANCOUNT_MCP_MCP_ENABLED` | `false` | Serve the MCP endpoint at `/mcp`. |
| `BEANCOUNT_MCP_MCP_RAW_TRANSACTIONS` | `false` | Also expose a tool that takes raw postings. Off by default, because recipes are safer. |
| `BEANCOUNT_MCP_AGENT_APPROVAL_REQUIRED` | `true` | Agent changes wait for approval. With `false` they are applied at once and recorded as approved. |
| `BEANCOUNT_MCP_IMPORT_MAX_BYTES` | `5000000` | The largest statement file that can be uploaded. |
| `BEANCOUNT_MCP_RECEIPTS_MAX_BYTES` | `15000000` | The largest receipt file that can be uploaded. |
| `BEANCOUNT_MCP_RECEIPTS_OCR_ENABLED` | `false` | Let agents read receipts as text: a PDF's own text, and OCR of pictures and scanned pages. Needs the `receipts` and `ocr` extras. Off, the agent has no receipt tool and is not told about receipts. |
| `BEANCOUNT_MCP_RECEIPTS_AGENT_IMAGES` | `false` | Also let agents see the receipt's picture. Separate from OCR because sending an image to a hosted model is a different decision. |
| `BEANCOUNT_MCP_RECEIPTS_OCR_BACKEND` | `rapidocr` | Which OCR backend reads pictures. Plugins can add others. |
| `BEANCOUNT_MCP_RECEIPTS_MAX_PAGES` | `10` | Pages of a PDF that are read. |
| `BEANCOUNT_MCP_REFERENCE_RATES_ENABLED` | `false` | Enable approximate, read-only reference valuations from Frankfurter. These values never drive ledger entries. |
| `BEANCOUNT_MCP_REFERENCE_RATES_URL` | `https://api.frankfurter.dev/v2` | Frankfurter v2 root. May point to a self-hosted instance. |
| `BEANCOUNT_MCP_REFERENCE_RATES_FRESH_HOURS` | `24` | How long a fetched rate remains fresh. |
| `BEANCOUNT_MCP_REFERENCE_RATES_STALE_HOURS` | `12` | Additional stale-while-revalidate grace period. |
| `BEANCOUNT_MCP_AUTH_TOKEN` | none | The bearer token for the whole service. A blank value means **no authentication**. |

Booleans accept `true` and `false`. Leave `AUTH_TOKEN` unset only on a loopback you trust.

## The env file

When running from source, settings also come from an env file: `.env` in the working directory, or the path in `BEANCOUNT_MCP_ENV_FILE`. `.env.example` in the repository lists the variables. `.env` is git-ignored.

## Secrets from a folder

For Docker secrets, point `BEANCOUNT_MCP_SECRETS_DIR` at a folder. A file named after a setting (for example `BEANCOUNT_MCP_AUTH_TOKEN`) supplies its value. This keeps the token out of the environment.

## Modes

| You want | Set |
| --- | --- |
| Agents connect through MCP | `MCP_ENABLED=true` |
| Only a harness plugin that calls the HTTP API directly | `MCP_ENABLED=false`. The REST API, including the agent surface, stays up. |
| Agents commit without review (not recommended) | `AGENT_APPROVAL_REQUIRED=false` |

There is no stdio transport. The service is one long-lived process, so approval, the web interface and the API stay available behind the MCP endpoint.

## Layout is fixed per ledger

The configured layout applies only when a ledger is created. Opening an existing ledger accepts any supported layout, and the layout recorded in the ledger's sidecar is authoritative. Changing a ledger's layout afterwards is not supported.
