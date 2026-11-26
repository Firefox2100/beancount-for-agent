import assert from "node:assert/strict";
import { test } from "node:test";

import { root, run, stubService } from "./helpers.js";

const change = {
  id: "c1",
  ledger_id: "main",
  status: "pending",
  note: null,
  created_at: "2026-03-01T10:00:00Z",
  caller: { actor: "agent", client_id: "mcp", session_id: null },
  operation: {
    kind: "add_transaction",
    transaction: {
      date: "2026-03-01",
      payee: null,
      narration: "Lunch",
      postings: [
        { account: "Expenses:Food", units: { number: "12.50", currency: "USD" } },
        { account: "Assets:Cash", units: { number: "-12.50", currency: "USD" } },
      ],
    },
  },
};

const review = (service, args, env = {}) =>
  run(`${root}/scripts/review`, args, { env: { BEANCOUNT_MCP_URL: service.url, ...env } });

test("pending lists proposals with their postings and sends the token", async () => {
  const service = await stubService({
    "GET /ledgers": { body: [{ id: "main" }] },
    "GET /ledgers/main/changes": { body: [change] },
  });
  const result = await review(service, ["pending"], { BEANCOUNT_MCP_AUTH_TOKEN: "secret" });
  await service.close();
  assert.equal(result.code, 0, result.stderr);
  assert.match(result.stdout, /c1 {2}\[main\] {2}pending/);
  assert.match(result.stdout, /from agent\/mcp/);
  assert.match(result.stdout, /add: 2026-03-01 Lunch/);
  assert.match(result.stdout, /Expenses:Food {2}12.50 USD/);
  assert.equal(service.requests[0].headers.authorization, "Bearer secret");
  assert.equal(service.requests[0].headers["x-actor"], "user");
  assert.equal(service.requests[1].query, "?status=pending");
});

test("the token can come from a file", async () => {
  const service = await stubService({ "GET /ledgers": { body: [] } });
  const { writeFileSync, mkdtempSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const dir = mkdtempSync(`${tmpdir()}/bc-`);
  writeFileSync(`${dir}/token`, "from-file\n");
  await review(service, ["pending"], { BEANCOUNT_MCP_TOKEN_FILE: `${dir}/token` });
  await service.close();
  assert.equal(service.requests[0].headers.authorization, "Bearer from-file");
});

test("with nothing pending it says so", async () => {
  const service = await stubService({
    "GET /ledgers": { body: [{ id: "main" }] },
    "GET /ledgers/main/changes": { body: [] },
  });
  const result = await review(service, ["pending"]);
  await service.close();
  assert.equal(result.stdout.trim(), "nothing pending");
  assert.equal(service.requests[0].headers.authorization, undefined);
});

test("approve posts a JSON body and reports the new status", async () => {
  const service = await stubService({
    "POST /ledgers/main/changes/c1/approve": { body: { ...change, status: "approved" } },
  });
  const result = await review(service, ["approve", "main", "c1"]);
  await service.close();
  assert.equal(result.stdout.trim(), "c1: approved");
  assert.deepEqual(JSON.parse(service.requests[0].body), { note: null });
  assert.equal(service.requests[0].headers["content-type"], "application/json");
});

test("reject carries the note", async () => {
  const service = await stubService({
    "POST /ledgers/main/changes/c1/reject": { body: { ...change, status: "rejected" } },
  });
  await review(service, ["reject", "main", "c1", "wrong", "account"]);
  await service.close();
  assert.deepEqual(JSON.parse(service.requests[0].body), { note: "wrong account" });
});

test("a refusal exits non-zero with the service's reason", async () => {
  const service = await stubService({
    "POST /ledgers/main/changes/c1/approve": { status: 409, body: { detail: "changed since it was proposed" } },
  });
  const result = await review(service, ["approve", "main", "c1"]);
  await service.close();
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /409: changed since it was proposed/);
});

test("details sets fields, clears them with a dash, and sends them as the user", async () => {
  const service = await stubService({ "PUT /ledgers/main/accounts/Assets:Bank/details": { body: { version: "v" } } });
  const result = await review(service, ["details", "main", "Assets:Bank", "sort_code=20 12 34", "bank_name=Barclays", "-iban"]);
  await service.close();
  assert.equal(result.stdout.trim(), "saved");
  assert.deepEqual(JSON.parse(service.requests[0].body), {
    set: { sort_code: "20 12 34", bank_name: "Barclays" },
    clear: ["iban"],
  });
  assert.equal(service.requests[0].headers["x-actor"], "user");
});

test("details with no fields shows them in full", async () => {
  const service = await stubService({
    "GET /ledgers/main/accounts": {
      body: [{ name: "Assets:Bank", details: { bank_name: "Barclays", account_number: "12345678" } }],
    },
  });
  const result = await review(service, ["details", "main", "Assets:Bank"]);
  await service.close();
  assert.match(result.stdout, /bank_name: Barclays/);
  assert.match(result.stdout, /account_number: 12345678/);
});

test("the token file may be the service's own env file", async () => {
  const service = await stubService({ "GET /ledgers": { body: [] } });
  const { writeFileSync, mkdtempSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const dir = mkdtempSync(`${tmpdir()}/bc-`);
  writeFileSync(`${dir}/env`, "# comment\nBEANCOUNT_MCP_MCP_ENABLED=true\nBEANCOUNT_MCP_AUTH_TOKEN=abc123\n");
  await review(service, ["pending"], { BEANCOUNT_MCP_TOKEN_FILE: `${dir}/env` });
  await service.close();
  assert.equal(service.requests[0].headers.authorization, "Bearer abc123");
});

test("due shows what is owed per currency", async () => {
  const service = await stubService({
    "GET /ledgers": { body: [{ id: "main" }] },
    "GET /ledgers/main/due": {
      body: [{ account: "Liabilities:Visa", due_date: "2026-03-20", owed: { USD: "120.00", CNY: "50.00" } }],
    },
  });
  const result = await review(service, ["due"]);
  await service.close();
  assert.match(result.stdout, /\[main\] Liabilities:Visa {2}due 2026-03-20 {2}120.00 USD, 50.00 CNY/);
});
