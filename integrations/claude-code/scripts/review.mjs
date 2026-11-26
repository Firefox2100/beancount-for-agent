#!/usr/bin/env node
// Review and resolve what the agent proposed, through the REST API. For the user, never the agent:
// only the slash commands call it. Needs Node 18 or newer and nothing else — no curl, no jq — so it
// runs the same on macOS, Linux and Windows.
//
//   review pending [LEDGER]        proposals waiting for approval, across ledgers
//   review show LEDGER ID          one proposal with its postings
//   review approve LEDGER ID       commit it
//   review reject LEDGER ID [NOTE] refuse it
//   review due [LEDGER]            what is due soon
//   review details LEDGER ACCOUNT [FIELD=VALUE ...] [-FIELD ...]
//                                  show an account's bank details in full, set fields, or
//                                  clear them with a leading dash. Run it in your own terminal:
//                                  anything typed into the chat is seen by the agent.
//
// Settings come from the environment or the token file, never from arguments:
//   BEANCOUNT_MCP_URL (default http://127.0.0.1:8000)
//   BEANCOUNT_MCP_AUTH_TOKEN, else the plugin's stored token (CLAUDE_PLUGIN_OPTION_API_TOKEN),
//   else the first line of BEANCOUNT_MCP_TOKEN_FILE
//   (default ~/.config/beancount-mcp/token)
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const USAGE = `review pending [LEDGER]        proposals waiting for approval, across ledgers
review show LEDGER ID          one proposal with its postings
review approve LEDGER ID       commit it
review reject LEDGER ID [NOTE] refuse it
review due [LEDGER]            what is due soon
review details LEDGER ACCOUNT [FIELD=VALUE ...] [-FIELD ...]
                               show an account's bank details in full, set fields, or clear
                               them with a leading dash`;

const out = (text) => process.stdout.write(text.endsWith("\n") ? text : `${text}\n`);
const fail = (text) => {
  process.stderr.write(`${text}\n`);
  process.exit(1);
};

const url = (process.env.BEANCOUNT_MCP_URL || process.env.CLAUDE_PLUGIN_OPTION_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

/** The token file is either `BEANCOUNT_MCP_AUTH_TOKEN=…`, or the service's env file: its first bare non-comment line. */
function tokenFromFile(file) {
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    return "";
  }
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const match = /^BEANCOUNT_MCP_AUTH_TOKEN=(.*)$/.exec(line);
    const value = match?.[1].replace(/\s+/g, "") ?? "";
    if (value !== "") return value;
  }
  for (const line of lines) {
    if (/^[^#=\s]+$/.test(line)) return line.replace(/\s+/g, "");
  }
  return "";
}

const token =
  process.env.BEANCOUNT_MCP_AUTH_TOKEN ||
  process.env.CLAUDE_PLUGIN_OPTION_API_TOKEN ||
  tokenFromFile(process.env.BEANCOUNT_MCP_TOKEN_FILE || join(homedir(), ".config", "beancount-mcp", "token"));

/** The service's own words for a refusal, whether it answered with `{detail}` or with plain text. */
function reason(text) {
  try {
    const detail = JSON.parse(text).detail;
    if (typeof detail === "string") return detail;
    if (detail !== undefined && detail !== null) return JSON.stringify(detail);
  } catch {
    // Not JSON: say what it said.
  }
  return text;
}

/** api METHOD PATH [JSON]: print the body, fail with the service's reason. */
async function api(method, path, body) {
  const headers = { "x-actor": "user", "x-client-id": "claude-code-review" };
  if (token !== "") headers.authorization = `Bearer ${token}`;
  if (body !== undefined) headers["content-type"] = "application/json";
  let response;
  try {
    response = await fetch(url + path, { method, headers, body, signal: AbortSignal.timeout(15000) });
  } catch {
    fail(`cannot reach ${url}`);
  }
  const text = await response.text();
  if (response.status >= 400) fail(`${response.status}: ${reason(text)}`);
  return text;
}

/** Ledgers to act on: the one named, or everyone the service knows. */
async function ledgerIds(argument) {
  if (argument !== undefined && argument !== "") return argument.split(/\s+/).filter((id) => id !== "");
  const ledgers = JSON.parse(await api("GET", "/ledgers"));
  return (Array.isArray(ledgers) ? ledgers : []).map((ledger) => ledger.id).filter((id) => typeof id === "string");
}

const posting = ({ account, units, price }) =>
  `    ${account}  ${units ? `${units.number} ${units.currency}` : ""}${price ? ` @ ${price.number} ${price.currency}` : ""}`;

/** One operation as reviewable lines, indented under the proposal. */
function operationLines(operation, prefix) {
  switch (operation?.kind) {
    case "add_transaction":
    case "update_transaction": {
      const transaction = operation.transaction ?? {};
      const label = operation.kind === "add_transaction" ? "add" : `update ${operation.id}`;
      const head = [transaction.date, transaction.payee, transaction.narration]
        .filter((value) => value !== null && value !== undefined && value !== "")
        .join(" ");
      const postings = (transaction.postings ?? []).map((entry) => `${prefix}${posting(entry)}`);
      return [`${prefix}${label}: ${head}`, ...postings];
    }
    case "batch":
      return (operation.operations ?? []).flatMap((entry) => operationLines(entry, `${prefix}  `));
    case "open_account":
      return [`${prefix}open ${operation.account}${operation.type ? ` (${operation.type})` : ""}`];
    case "close_account":
      return [`${prefix}close ${operation.account}`];
    case "reconcile":
      return [
        `${prefix}reconcile ${operation.account} to ${operation.amount.number} ${operation.amount.currency} on ${operation.date}`,
      ];
    default:
      return [`${prefix}${operation?.kind ?? ""}`];
  }
}

/** One proposal as reviewable text. */
function format(change) {
  const caller = [change.caller?.actor, change.caller?.client_id]
    .filter((value) => value !== null && value !== undefined && value !== "")
    .join("/");
  const lines = [`${change.id}  [${change.ledger_id}]  ${change.status}`, `from ${caller}`];
  if (change.note) lines.push(`note: ${change.note}`);
  return [...lines, ...operationLines(change.operation, "")].join("\n");
}

const owed = (amounts) =>
  Object.entries(amounts ?? {})
    .map(([currency, value]) => `${value} ${currency}`)
    .join(", ");

const [command, ...args] = process.argv.slice(2);

switch (command) {
  case "pending": {
    const ids = await ledgerIds(args[0]);
    let found = false;
    for (const ledger of ids) {
      const list = JSON.parse(await api("GET", `/ledgers/${ledger}/changes?status=pending`));
      const proposals = (Array.isArray(list) ? list : []).sort((left, right) =>
        String(left.created_at ?? "").localeCompare(String(right.created_at ?? "")),
      );
      if (proposals.length === 0) continue;
      found = true;
      for (const change of proposals) process.stdout.write(`${format(change)}\n\n`);
    }
    if (!found) out("nothing pending");
    break;
  }
  case "show": {
    if (args.length < 2) fail("usage: review show LEDGER ID");
    out(format(JSON.parse(await api("GET", `/ledgers/${args[0]}/changes/${args[1]}`))));
    break;
  }
  case "approve":
  case "reject": {
    if (args.length < 2) fail(`usage: review ${command} LEDGER ID [NOTE]`);
    const note = args.slice(2).join(" ");
    const result = JSON.parse(await api("POST", `/ledgers/${args[0]}/changes/${args[1]}/${command}`, JSON.stringify({ note: note === "" ? null : note })));
    out(`${args[1]}: ${result.status}`);
    break;
  }
  case "due": {
    const ids = await ledgerIds(args[0]);
    for (const ledger of ids) {
      const due = JSON.parse(await api("GET", `/ledgers/${ledger}/due?within_days=14`));
      if (!Array.isArray(due) || due.length === 0) {
        out(`[${ledger}] nothing due in 14 days`);
        continue;
      }
      for (const bill of due) out(`[${ledger}] ${bill.account}  due ${bill.due_date ?? "?"}  ${owed(bill.owed)}`);
    }
    break;
  }
  case "details": {
    if (args.length < 2) fail("usage: review details LEDGER ACCOUNT [FIELD=VALUE ...] [-FIELD ...]");
    const [ledger, account, ...fields] = args;
    if (fields.length === 0) {
      const accounts = JSON.parse(await api("GET", `/ledgers/${ledger}/accounts`));
      const found = (Array.isArray(accounts) ? accounts : []).find((entry) => entry.name === account);
      if (found === undefined) fail(`no such account: ${account}`);
      const details = Object.entries(found.details ?? {});
      if (details.length === 0) out("no details set");
      else for (const [field, value] of details) out(`${field}: ${value}`);
      break;
    }
    const body = { set: {}, clear: [] };
    for (const field of fields) {
      if (field.startsWith("-")) body.clear.push(field.slice(1));
      else if (field.includes("=")) {
        const at = field.indexOf("=");
        body.set[field.slice(0, at)] = field.slice(at + 1);
      } else fail(`expected FIELD=VALUE or -FIELD, got: ${field}`);
    }
    await api("PUT", `/ledgers/${ledger}/accounts/${account}/details`, JSON.stringify(body));
    out("saved");
    break;
  }
  default:
    process.stderr.write(`${USAGE}\n`);
    process.exit(2);
}
